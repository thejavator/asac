"""A developer runs the CLI, then opens the portal on the same project: both must see one run."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from asac.cli import app as cli_app
from asac.portal.app import PortalSettings, create_app
from asac.portal.oidc import Identity
from tests.conftest import init_git
from tests.seed import seed_single

runner = CliRunner()
PERSONAS = {"dev": Identity("dev-sub", "Dev", frozenset({"developer", "admin"}))}


@pytest.fixture
def dev_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASAC_ENV", "dev")
    monkeypatch.setenv("ASAC_FIXED_TIME", "2026-01-01T00:00:00Z")


def _cli(project: Path, *args: str):  # type: ignore[no-untyped-def]
    return runner.invoke(cli_app, [*args, "-f", str(project / "asac.yaml")])


def _client(data: Path) -> TestClient:
    settings = PortalSettings(
        data_dir=data, dev_personas=PERSONAS, harness="fake", secure_cookie=False,
        shared_state=True,
    )  # fmt: skip
    c = TestClient(create_app(settings), follow_redirects=False)
    assert c.get("/login?persona=dev").status_code == 303
    return c


def test_a_run_started_by_the_cli_is_listed_by_the_portal(
    sandbox_project: Path, dev_env: None
) -> None:
    """The defect: the CLI keeps its state in ASAC_STATE_DIR, the portal looked in a folder named
    after the project. A project registered in the portal showed no run at all."""
    init_git(sandbox_project)
    r = _cli(sandbox_project, "apply", "-p", "feature", "--harness", "fake", "--run-id", "cli1")
    assert r.exit_code == 2, r.output
    data = seed_single(sandbox_project.parent / "portal-data", sandbox_project / "asac.yaml")
    client = _client(data)
    runs = client.get("/api/v1/projects/default/runs")
    assert runs.status_code == 200, runs.text
    assert "cli1" in runs.text, runs.text


def test_the_gate_of_a_cli_run_can_be_decided_from_the_portal(
    sandbox_project: Path, dev_env: None
) -> None:
    init_git(sandbox_project)
    _cli(sandbox_project, "apply", "-p", "feature", "--harness", "fake", "--run-id", "cli2")
    client = _client(
        seed_single(sandbox_project.parent / "portal-data", sandbox_project / "asac.yaml")
    )
    gates = client.get("/api/v1/projects/default/gates")
    assert "gate_cli2_requirements" in gates.text, gates.text
    assert subprocess.run(["git", "status", "--porcelain"], cwd=sandbox_project,
                          capture_output=True, text=True).stdout == ""  # fmt: skip


def test_central_mode_keeps_each_project_state_separate(
    sandbox_project: Path, dev_env: None
) -> None:
    """Central mode (shared_state off) must not show the CLI's run: projects stay isolated."""
    init_git(sandbox_project)
    _cli(sandbox_project, "apply", "-p", "feature", "--harness", "fake", "--run-id", "cli3")
    data = seed_single(sandbox_project.parent / "portal-data", sandbox_project / "asac.yaml")
    settings = PortalSettings(
        data_dir=data, dev_personas=PERSONAS, harness="fake", secure_cookie=False
    )
    c = TestClient(create_app(settings), follow_redirects=False)
    c.get("/login?persona=dev")
    assert "cli3" not in c.get("/api/v1/projects/default/runs").text


def test_two_projects_in_central_mode_do_not_see_each_others_runs(
    sandbox_project: Path, dev_env: None, tmp_path: Path
) -> None:
    import shutil

    other = tmp_path / "other"
    shutil.copytree(sandbox_project, other)
    init_git(other)
    data = seed_single(tmp_path / "portal-data", sandbox_project / "asac.yaml", "alpha")
    seed_single(tmp_path / "portal-data", other / "asac.yaml", "beta")
    settings = PortalSettings(
        data_dir=data, dev_personas=PERSONAS, harness="fake", secure_cookie=False
    )
    from asac.engine.apply import create_run, execute
    from asac.engine.runtime import make_context, store_for
    from asac.loader.load import load_manifest

    manifest = load_manifest(sandbox_project / "asac.yaml")
    ctx = make_context(
        manifest, "feature", store_for(sandbox_project / "asac.yaml", "alpha"),
        sandbox_project, "fake", project="alpha",
    )  # fmt: skip
    create_run(ctx, "only-alpha")
    execute(ctx, "only-alpha")
    c = TestClient(create_app(settings), follow_redirects=False)
    c.get("/login?persona=dev")
    assert "only-alpha" in c.get("/api/v1/projects/alpha/runs").text
    assert "only-alpha" not in c.get("/api/v1/projects/beta/runs").text


# -- `asac portal --local` ----------------------------------------------------------------------


def _local(project: Path, monkeypatch: pytest.MonkeyPatch, *args: str):  # type: ignore[no-untyped-def]
    from asac import cli

    served: dict[str, object] = {}
    monkeypatch.setattr(cli, "_serve", lambda a, host, port: served.update(app=a, host=host))
    monkeypatch.delenv("ASAC_OIDC_ISSUER", raising=False)
    r = runner.invoke(cli_app, ["portal", "--local", "-f", str(project / "asac.yaml"), *args])
    return r, served


def test_local_mode_needs_no_environment_variable_and_registers_the_project(
    sandbox_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("ASAC_ENV", raising=False)  # the developer sets nothing
    monkeypatch.setenv("ASAC_FIXED_TIME", "2026-01-01T00:00:00Z")
    init_git(sandbox_project)
    _cli(sandbox_project, "apply", "-p", "feature", "--harness", "fake", "--run-id", "loc1")
    r, served = _local(sandbox_project, monkeypatch)
    assert r.exit_code == 0, r.output
    assert served["host"] == "127.0.0.1"
    c = TestClient(served["app"], follow_redirects=False)  # type: ignore[arg-type]
    assert c.get("/login?persona=dev").status_code == 303
    projects = c.get("/api/v1/projects")
    assert projects.status_code == 200 and sandbox_project.name in projects.text, projects.text
    pid = projects.json()[0]["id"] if isinstance(projects.json(), list) else None
    assert pid, projects.text
    assert "loc1" in c.get(f"/api/v1/projects/{pid}/runs").text


def test_local_mode_refuses_a_public_address(
    sandbox_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No identity means it must never leave the machine."""
    r, served = _local(sandbox_project, monkeypatch, "--host", "0.0.0.0")
    assert r.exit_code == 1 and "127.0.0.1" in r.output
    assert "app" not in served


def test_local_mode_refuses_oidc(sandbox_project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASAC_OIDC_ISSUER", "https://idp.example")
    from asac import cli

    monkeypatch.setattr(cli, "_serve", lambda a, host, port: None)
    r = runner.invoke(cli_app, ["portal", "--local", "-f", str(sandbox_project / "asac.yaml")])
    assert r.exit_code == 1 and "OIDC" in r.output


def test_local_mode_says_what_it_is(sandbox_project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    r, _ = _local(sandbox_project, monkeypatch)
    assert "local" in r.output.lower() and "no sign-in" in r.output.lower()


def test_restarting_the_local_portal_does_not_duplicate_the_project(
    sandbox_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for _ in range(2):
        r, served = _local(sandbox_project, monkeypatch)
        assert r.exit_code == 0, r.output
    c = TestClient(served["app"], follow_redirects=False)  # type: ignore[arg-type]
    c.get("/login?persona=dev")
    assert len(c.get("/api/v1/projects").json()) == 1


def test_the_local_portal_folder_does_not_make_the_repository_dirty(
    sandbox_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    init_git(sandbox_project)
    _local(sandbox_project, monkeypatch)
    status = subprocess.run(["git", "status", "--porcelain"], cwd=sandbox_project,
                            capture_output=True, text=True).stdout  # fmt: skip
    assert status == "", status


# -- central mode: `asac portal --project ID=PATH` ------------------------------------------------


def _central(data: Path, monkeypatch: pytest.MonkeyPatch, *args: str):  # type: ignore[no-untyped-def]
    from asac import cli

    served: dict[str, object] = {}
    monkeypatch.setattr(cli, "_serve", lambda a, host, port: served.update(app=a, host=host))
    monkeypatch.setenv("ASAC_ENV", "dev")
    monkeypatch.delenv("ASAC_OIDC_ISSUER", raising=False)
    r = runner.invoke(cli_app, ["portal", "--data", str(data), *args])
    return r, served


def test_a_project_given_at_startup_is_registered_once(
    sandbox_project: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    data = tmp_path / "central"
    spec = f"payments={sandbox_project / 'asac.yaml'}"
    for _ in range(2):  # a pod restarts: the same flag must not fail or duplicate
        r, served = _central(data, monkeypatch, "--project", spec)
        assert r.exit_code == 0, r.output
    c = TestClient(served["app"], follow_redirects=False)  # type: ignore[arg-type]
    c.get("/login?persona=po")
    ids = [p["id"] for p in c.get("/api/v1/projects").json()]
    assert ids == ["payments"], ids


def test_a_startup_project_does_not_share_state_with_the_cli(
    sandbox_project: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Central mode keeps one state per project: it is not the developer's CLI state."""
    init_git(sandbox_project)
    _cli(sandbox_project, "apply", "-p", "feature", "--harness", "fake", "--run-id", "dev-run")
    r, served = _central(tmp_path / "central", monkeypatch, "--project",
                         f"payments={sandbox_project / 'asac.yaml'}")  # fmt: skip
    c = TestClient(served["app"], follow_redirects=False)  # type: ignore[arg-type]
    c.get("/login?persona=po")
    assert "dev-run" not in c.get("/api/v1/projects/payments/runs").text


@pytest.mark.parametrize("bad", ["noequals", "=/x/asac.yaml", "Bad_Id=/x/asac.yaml", "ok="])
def test_a_malformed_project_option_is_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, bad: str
) -> None:
    r, served = _central(tmp_path / "central", monkeypatch, "--project", bad)
    assert r.exit_code == 1 and "--project" in r.output
    assert "app" not in served


def test_a_project_whose_manifest_is_missing_is_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    r, served = _central(tmp_path / "central", monkeypatch, "--project",
                         f"x={tmp_path / 'nope' / 'asac.yaml'}")  # fmt: skip
    assert r.exit_code == 1 and "does not exist" in r.output
    assert "app" not in served


# -- a run started from the portal goes through the engine (worktree, isolation) -------------


def _tool(tmp_path: Path) -> Path:
    bindir = tmp_path / "bin"
    bindir.mkdir(exist_ok=True)
    exe = bindir / "claude"
    exe.write_text(
        "#!/bin/sh\n"
        'printf "# Spec\\n## Acceptance criteria\\n- ok\\n" > SPEC.md\n'
        'echo \'{"type":"result","is_error":false,"total_cost_usd":0.01,'
        '"usage":{},"result":"x"}\'\n'
    )
    exe.chmod(0o755)
    return bindir


def _portal_on(project: Path, tmp_path: Path) -> TestClient:
    settings = PortalSettings(
        data_dir=seed_single(tmp_path / "portal-data", project / "asac.yaml"),
        dev_personas=PERSONAS, harness="claude-code", secure_cookie=False,
        shared_state=True, run_inline=True,
    )  # fmt: skip
    c = TestClient(create_app(settings), follow_redirects=False)
    c.get("/login?persona=dev")
    return c


def _start(c: TestClient) -> str:
    csrf = c.get("/api/v1/me").json()["csrf"]
    r = c.post("/api/v1/projects/default/runs", json={"pipeline": "feature"},
               headers={"X-CSRF-Token": csrf})  # fmt: skip
    assert r.status_code in (200, 201, 202), r.text
    return str(r.json()["run_id"])


@pytest.fixture
def real_tools(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    import shutil

    root = tmp_path / "rt"
    shutil.copytree(Path(__file__).resolve().parent.parent / "examples" / "real-tools", root,
                    ignore=shutil.ignore_patterns(".DS_Store", ".asac-state"))  # fmt: skip
    shutil.copy(root / "vars" / "claude-code.yaml", root / "asac.vars.yaml")
    init_git(root)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("ASAC_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("ASAC_ENV", "dev")
    monkeypatch.setenv("ASAC_FIXED_TIME", "2026-01-01T00:00:00Z")
    monkeypatch.setenv("ASAC_AUTORUN", "1")
    monkeypatch.setenv("ASAC_SANDBOX", "0")
    monkeypatch.setenv("PATH", f"{_tool(tmp_path)}:/usr/bin:/bin")
    return root


def test_a_run_started_from_the_portal_gets_its_own_worktree(
    real_tools: Path, tmp_path: Path
) -> None:
    run_id = _start(_portal_on(real_tools, tmp_path))
    work = tmp_path / "state" / "worktrees" / run_id
    assert work.is_dir(), "the portal run has no worktree: the agent worked in the main checkout"
    assert (work / "SPEC.md").is_file()


def test_a_run_started_from_the_portal_leaves_the_main_checkout_clean(
    real_tools: Path, tmp_path: Path
) -> None:
    _start(_portal_on(real_tools, tmp_path))
    status = subprocess.run(["git", "status", "--porcelain"], cwd=real_tools,
                            capture_output=True, text=True).stdout  # fmt: skip
    assert status == "", status


def test_a_portal_run_is_audited_like_a_cli_run(real_tools: Path, tmp_path: Path) -> None:
    from asac.engine.runtime import store_for

    run_id = _start(_portal_on(real_tools, tmp_path))
    actions = [a.action for a in store_for(real_tools / "asac.yaml").audit(run_id)]
    assert "workspace.created" in actions and "step.committed" in actions, actions
