"""What the Decision Room shows a person before they sign: due date, cost, checks, evidence."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from asac.portal.app import PortalSettings, create_app
from asac.portal.oidc import Identity
from tests.conftest import init_git
from tests.seed import seed_single

PERSONAS = {"po": Identity("po-sub", "Camille", frozenset({"product_owner"}))}
EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "real-tools"


@pytest.fixture
def started(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """real-tools with one run that stopped at the requirements gate, seen through the portal."""
    root = tmp_path / "rt"
    shutil.copytree(EXAMPLE, root, ignore=shutil.ignore_patterns(".DS_Store", ".asac-state"))
    shutil.copy(root / "vars" / "claude-code.yaml", root / "asac.vars.yaml")
    init_git(root)
    bindir = tmp_path / "bin"
    bindir.mkdir()
    (bindir / "claude").write_text(
        "#!/bin/sh\n"
        'printf "# Spec\\n## Acceptance criteria\\n- ok\\n" > SPEC.md\n'
        'echo \'{"type":"result","is_error":false,"total_cost_usd":0.42,'
        '"usage":{"input_tokens":10},"result":"x"}\'\n'
    )
    (bindir / "claude").chmod(0o755)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("ASAC_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("ASAC_ENV", "dev")
    monkeypatch.setenv("ASAC_FIXED_TIME", "2026-01-01T09:00:00Z")
    monkeypatch.setenv("ASAC_AUTORUN", "1")
    monkeypatch.setenv("ASAC_SANDBOX", "0")
    monkeypatch.setenv("PATH", f"{bindir}:/usr/bin:/bin")
    settings = PortalSettings(
        data_dir=seed_single(tmp_path / "portal-data", root / "asac.yaml"),
        dev_personas=PERSONAS, harness="claude-code", secure_cookie=False,
        shared_state=True, run_inline=True,
    )  # fmt: skip
    c = TestClient(create_app(settings), follow_redirects=False)
    c.get("/login?persona=po")
    csrf = c.get("/api/v1/me").json()["csrf"]
    r = c.post("/api/v1/projects/default/runs", json={"pipeline": "feature"},
               headers={"X-CSRF-Token": csrf})  # fmt: skip
    assert r.status_code in (200, 201, 202), r.text
    return c


def _decision(c: TestClient) -> dict:  # type: ignore[type-arg]
    items = c.get("/api/v1/decisions").json()
    assert items, "no pending decision"
    return items[0]  # type: ignore[no-any-return]


def test_each_pending_decision_names_its_pipeline(started: TestClient) -> None:
    assert _decision(started)["pipeline"] == "feature"


def test_the_decision_carries_the_cost_so_far_and_when_the_run_started(started: TestClient) -> None:
    d = _decision(started)
    assert d["cost_usd"] == pytest.approx(0.42)
    assert d["run_started_at"] == "2026-01-01T09:00:00Z"


def test_the_decision_carries_the_commit_it_approves(started: TestClient) -> None:
    d = _decision(started)
    assert d["subject"] and len(d["subject"]) == 40  # a full sha


def test_the_decision_lists_the_checks_the_step_ran_with_their_moment(started: TestClient) -> None:
    checks = _decision(started)["checks"]
    got = [(c["kind"], c["moment"], c["name"], c["passed"]) for c in checks if c["kind"] == "hook"]
    assert got == [
        ("hook", "pre_tool", "no-secrets", True),
        ("hook", "pre_tool", "step-scope", True),
        ("hook", "post_step", "step-scope", True),
    ], got


def test_checks_of_another_step_are_not_shown(started: TestClient) -> None:
    names = [c["name"] for c in _decision(started)["checks"]]
    assert "tests-green" not in names  # that hook belongs to development, not requirements


def test_a_failed_hook_is_shown_as_failed_with_its_output() -> None:
    from asac.portal.decision import checks_from_audit
    from asac.ports.state import AuditRecord

    rows = [AuditRecord(1, "t", "r", "s1", "cli", "hook.failed",
                        "post_step tests-green\n2 tests failed")]  # fmt: skip
    (c,) = checks_from_audit(rows, "s1")
    assert (c.name, c.moment, c.passed, c.output) == ("tests-green", "post_step", False,
                                                      "2 tests failed")  # fmt: skip


def test_an_audit_without_the_moment_is_still_listed_without_inventing_one() -> None:
    from asac.portal.decision import checks_from_audit
    from asac.ports.state import AuditRecord

    (c,) = checks_from_audit(
        [AuditRecord(1, "t", "r", "s1", "cli", "hook.passed", "no-secrets")], "s1"
    )
    assert c.name == "no-secrets" and c.moment == ""


def test_urgency_is_computed_from_the_due_time() -> None:
    from asac.portal.decision import urgency

    now = "2026-01-01T09:00:00Z"
    assert urgency("2026-01-01T12:00:00Z", now) == ("soon", 3 * 3600)
    assert urgency("2026-01-01T08:00:00Z", now) == ("late", -3600)
    assert urgency("2026-01-03T09:00:00Z", now)[0] == "none"
    assert urgency(None, now) == ("none", None)


def test_the_decision_lists_the_files_the_approved_commit_changed(started: TestClient) -> None:
    files = _decision(started)["files"]
    paths = {f["path"]: f["change"] for f in files}
    assert paths.get("SPEC.md") == "added", paths
    assert not any(p.startswith(".asac-state") or "__pycache__" in p for p in paths), paths


def test_changed_files_come_from_the_commit_and_nothing_else(tmp_path: Path) -> None:
    import subprocess

    from asac.portal.decision import changed_files

    def git(*a: str) -> str:
        proc = subprocess.run(
            ["git", "-c", "user.email=t@t", "-c", "user.name=t", *a],
            cwd=tmp_path,
            check=True,
            capture_output=True,
            text=True,
        )
        return proc.stdout.strip()

    git("init", "-q", "-b", "main")
    (tmp_path / "keep.txt").write_text("1")
    (tmp_path / "gone.txt").write_text("1")
    git("add", "-A")
    git("commit", "-q", "-m", "base")
    (tmp_path / "keep.txt").write_text("2")
    (tmp_path / "gone.txt").unlink()
    (tmp_path / "new.txt").write_text("n")
    git("add", "-A")
    git("commit", "-q", "-m", "step")
    (tmp_path / "later.txt").write_text("not in that commit")
    got = {f.path: f.change for f in changed_files(tmp_path, git("rev-parse", "HEAD"))}
    assert got == {"keep.txt": "modified", "gone.txt": "deleted", "new.txt": "added"}


def test_a_missing_worktree_or_unknown_commit_gives_no_files_rather_than_an_error(
    tmp_path: Path,
) -> None:
    from asac.portal.decision import changed_files

    assert changed_files(tmp_path / "nope", "0" * 40) == []
    assert changed_files(tmp_path, "not-a-sha") == []  # refused before reaching git


def test_an_option_shaped_commit_id_is_never_given_to_git(tmp_path: Path) -> None:
    """`git show --output=FILE` writes FILE. The id comes from the database, but it reaches git,
    so it must be a full commit id. Checked in a real repository, on the disk: in a folder that is
    not a repository git fails before doing anything and the test would prove nothing."""
    import subprocess

    from asac.portal.decision import changed_files

    repo = tmp_path / "repo"
    repo.mkdir()
    for args in (["init", "-q", "-b", "main"], ["commit", "-q", "--allow-empty", "-m", "x"]):
        subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", *args],
                       cwd=repo, check=True, capture_output=True)  # fmt: skip
    planted = tmp_path / "PLANTED"
    for evil in (f"--output={planted}", "HEAD", "HEAD~0", "main", "-p"):
        assert changed_files(repo, evil) == [], evil
    assert not planted.exists(), "git was run with an option taken from the commit id"


@pytest.mark.parametrize(
    "path,mounted",
    [
        (".claude/skills/impl/SKILL.md", True),
        ("CLAUDE.md", True),
        ("AGENTS.md", True),
        (".cursor/rules/asac-spec.mdc", True),
        (".bob/skills/spec/SKILL.md", True),
        (".mcp.json", True),
        ("app/todo/__init__.py", False),
        ("SPEC.md", False),
        ("docs/CLAUDE.md", False),  # only the root file is ASAC's mount
        (".claude/settings.json", False),  # not a skill: an agent may really have written it
    ],
)
def test_files_asac_mounts_for_the_tool_are_told_apart_from_the_agents_work(
    path: str, mounted: bool
) -> None:
    from asac.portal.decision import is_asac_mount

    assert is_asac_mount(path) is mounted


def test_the_decision_marks_mounted_files_and_keeps_them_listed(started: TestClient) -> None:
    files = {f["path"]: f["mounted"] for f in _decision(started)["files"]}
    assert files["SPEC.md"] is False
    assert files[".claude/skills/spec/SKILL.md"] is True
    assert "CLAUDE.md" in files, "a mounted file must stay visible to the reviewer"


def test_the_files_shown_come_from_the_real_commit_not_from_a_repository_the_agent_made(
    tmp_path: Path,
) -> None:
    """The worktree's `.git` is a file the agent can rewrite. The portal reads the real git
    directory, found from the main repository, so a made-up repository shows nothing."""
    import subprocess

    from asac.engine.workspace import create_workspace
    from asac.portal.decision import changed_files

    def git(cwd: Path, *a: str) -> str:
        cmd = ["git", "-c", "user.email=t@t", "-c", "user.name=t", *a]
        done = subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, text=True)
        return done.stdout.strip()

    root = tmp_path / "main"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    (root / "a.txt").write_text("a")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "base")
    ws = create_workspace(root, tmp_path / "state", "r1")
    (ws.path / "real.py").write_text("real = 1\n")
    git(ws.path, "add", "-A")
    git(ws.path, "commit", "-q", "-m", "the work")
    sha = git(ws.path, "rev-parse", "HEAD")
    assert {f.path for f in changed_files(ws.path, sha, root)} == {"real.py"}
    # the agent points .git at a repository it made, with a different history
    fake = ws.path / ".fake"
    subprocess.run(["git", "init", "-q", "-b", "main", str(fake)], check=True, capture_output=True)
    (ws.path / ".git").write_text(f"gitdir: {fake / '.git'}\n")
    assert {f.path for f in changed_files(ws.path, sha, root)} == {"real.py"}  # still the real one
