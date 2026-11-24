"""Daemon webhook (HMAC, filters, idempotency) and Runner placement."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from asac.adapters import state_dir
from asac.adapters.artifacts_fs import FsArtifactStore
from asac.adapters.runner_local import DockerRunner, FakeRunner, container_name
from asac.daemon.app import create_app
from asac.daemon.triggers import parse_jira, sign
from asac.engine.runtime import store_for

SECRET = "s3cret"


def payload(labels: list[str]) -> bytes:
    return json.dumps(
        {
            "webhookEvent": "jira:issue_created",
            "issue": {"key": "PAY-1", "fields": {"issuetype": {"name": "Story"}, "labels": labels}},
        }
    ).encode()


@pytest.fixture(autouse=True)
def env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASAC_WEBHOOK_SECRET", SECRET)
    monkeypatch.setenv("ASAC_FIXED_TIME", "2026-01-01T00:00:00Z")


def post(client: TestClient, body: bytes, sig: str | None):
    headers = {"X-Hub-Signature-256": sig} if sig else {}
    return client.post("/webhooks/jira", content=body, headers=headers)


def test_bad_signature_refused(sandbox_project: Path) -> None:
    client = TestClient(create_app(sandbox_project / "asac.yaml", "fake"))
    assert post(client, payload(["asac-enabled"]), "sha256=bad").status_code == 401
    assert post(client, payload(["asac-enabled"]), None).status_code == 401


def test_missing_secret_is_503(sandbox_project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ASAC_WEBHOOK_SECRET")
    client = TestClient(create_app(sandbox_project / "asac.yaml", "fake"))
    assert post(client, b"{}", "sha256=x").status_code == 503


def test_label_filter_and_idempotent_replay(sandbox_project: Path) -> None:
    client = TestClient(create_app(sandbox_project / "asac.yaml", "fake"))
    body = payload([])
    assert post(client, body, sign(SECRET, body)).json()["status"] == "ignored"
    body = payload(["asac-enabled"])
    first = post(client, body, sign(SECRET, body)).json()
    assert first["status"] == "accepted"
    run_id = first["runs"][0]["run_id"]
    again = post(client, body, sign(SECRET, body)).json()
    assert again["runs"][0]["run_id"] == run_id
    store = store_for(sandbox_project / "asac.yaml")
    created = [a for a in store.audit(run_id) if a.action == "run.created"]
    assert len(created) == 1


def test_invalid_json_and_non_issue(sandbox_project: Path) -> None:
    client = TestClient(create_app(sandbox_project / "asac.yaml", "fake"))
    assert post(client, b"nope", sign(SECRET, b"nope")).status_code == 400
    assert parse_jira({"webhookEvent": "comment_created"}) is None


def test_fake_runner_contract() -> None:
    r = FakeRunner()
    h = r.start("run1", "s1")
    r.stop(h)
    assert r.started == [("run1", "s1")] and r.stopped == [h]
    assert FakeRunner(up=False).available() is False


def test_docker_command_is_locked_down(tmp_path: Path) -> None:
    cmd = DockerRunner(tmp_path, docker="docker").command("run 1", "s/1")
    joined = " ".join(cmd)
    for flag in ("--network none", "--read-only", "--cap-drop ALL", "no-new-privileges"):
        assert flag in joined
    assert "65534" in joined
    assert container_name("run 1", "s/1") == "asac-run-1-s-1"


def _delegate_project(project: Path, fallback: bool) -> None:
    f = project / "asac.yaml"
    text = f.read_text()
    if fallback:  # the example declares the runner; only the development step falls back
        text = text.replace(
            "execution: { runner: docker }", "execution: { runner: docker, fallback: assist }", 1
        )
    f.write_text(text)


def _run(project: Path, runner: FakeRunner):  # type: ignore[no-untyped-def]
    from asac.engine.apply import create_run, decide_gate, execute
    from asac.engine.runtime import make_context
    from asac.loader.load import load_manifest

    manifest = load_manifest(project / "asac.yaml")
    store = store_for(project / "asac.yaml")
    ctx = make_context(manifest, "feature", store, project, "fake", runner)
    create_run(ctx, "r1")
    execute(ctx, "r1")
    decide_gate(store, "gate_r1_requirements", "approved", "po", {"product_owner"}, None)
    return execute(ctx, "r1"), store


def test_runner_started_and_stopped(sandbox_project: Path) -> None:
    _delegate_project(sandbox_project, fallback=False)
    runner = FakeRunner()
    _run(sandbox_project, runner)
    assert runner.started == [("r1", "development")]
    assert runner.stopped == ["fake-r1-development"]


def test_runner_down_falls_back_to_assist(sandbox_project: Path) -> None:
    _delegate_project(sandbox_project, fallback=True)
    out, store = _run(sandbox_project, FakeRunner(up=False))
    assert int(out.code) == 2 and "handed to a person" in out.message
    assert store.get_step_status("r1", "development") == "handoff"


def test_runner_down_without_fallback_blocks(sandbox_project: Path) -> None:
    _delegate_project(sandbox_project, fallback=False)
    out, _ = _run(sandbox_project, FakeRunner(up=False))
    assert int(out.code) == 3


def test_cli_servers_refuse_without_config(sandbox_project: Path, monkeypatch: pytest.MonkeyPatch):
    from typer.testing import CliRunner

    from asac.cli import app

    monkeypatch.delenv("ASAC_WEBHOOK_SECRET")
    monkeypatch.delenv("ASAC_ENV", raising=False)
    monkeypatch.delenv("ASAC_OIDC_ISSUER", raising=False)
    f = str(sandbox_project / "asac.yaml")
    assert CliRunner().invoke(app, ["daemon", "-f", f]).exit_code == 1
    assert CliRunner().invoke(app, ["portal"]).exit_code == 1


def _github_body(action: str = "opened", labels: tuple[str, ...] = ("asac-enabled",)) -> bytes:
    return json.dumps(
        {
            "action": action,
            "issue": {"number": 12, "labels": [{"name": x} for x in labels]},
        }
    ).encode()


def _gitlab_body(action: str = "open", labels: tuple[str, ...] = ("asac-enabled",)) -> bytes:
    return json.dumps(
        {
            "object_kind": "issue",
            "object_attributes": {"iid": 12, "action": action, "issue_type": "issue"},
            "labels": [{"title": x} for x in labels],
        }
    ).encode()


def _with_trigger(project: Path, provider: str, event: str) -> Path:
    f = project / "asac.yaml"
    f.write_text(
        f.read_text().replace("provider: jira", f"provider: {provider}")
        .replace("event: issue_created", f"event: {event}")
        .replace("issuetype: Story, ", "")
    )  # fmt: skip
    return f


def test_github_issue_starts_a_run_and_records_where_it_came_from(sandbox_project: Path) -> None:
    f = _with_trigger(sandbox_project, "github", "issue_opened")
    client = TestClient(create_app(f, "fake"))
    body = _github_body()
    sig = {"X-Hub-Signature-256": sign(SECRET, body), "X-GitHub-Event": "issues"}
    first = client.post("/webhooks/github", content=body, headers=sig).json()
    assert first["status"] == "accepted" and first["runs"][0]["run_id"].endswith("_12")
    client.post("/webhooks/github", content=body, headers=sig)  # replay
    audit = store_for(f).audit(first["runs"][0]["run_id"])
    assert [a.detail for a in audit if a.action == "run.triggered"] == ["github:12:issue_opened"]
    bad = {"X-Hub-Signature-256": "sha256=bad", "X-GitHub-Event": "issues"}
    assert client.post("/webhooks/github", content=body, headers=bad).status_code == 401
    other = {"X-Hub-Signature-256": sign(SECRET, body), "X-GitHub-Event": "push"}
    assert client.post("/webhooks/github", content=body, headers=other).json()["runs"] == []
    no_label = _github_body(labels=())
    hdr = {"X-Hub-Signature-256": sign(SECRET, no_label), "X-GitHub-Event": "issues"}
    assert client.post("/webhooks/github", content=no_label, headers=hdr).json()["runs"] == []


def test_gitlab_issue_uses_the_shared_token(sandbox_project: Path) -> None:
    f = _with_trigger(sandbox_project, "gitlab", "issue_opened")
    client = TestClient(create_app(f, "fake"))
    body = _gitlab_body()
    assert client.post("/webhooks/gitlab", content=body).status_code == 401
    wrong = {"X-Gitlab-Token": "nope"}
    assert client.post("/webhooks/gitlab", content=body, headers=wrong).status_code == 401
    ok = client.post("/webhooks/gitlab", content=body, headers={"X-Gitlab-Token": SECRET})
    assert ok.json()["status"] == "accepted"
    closed = _gitlab_body(action="close")
    out = client.post("/webhooks/gitlab", content=closed, headers={"X-Gitlab-Token": SECRET})
    assert out.json()["runs"] == []


def test_hostile_issue_key_never_becomes_a_run_id(sandbox_project: Path) -> None:
    client = TestClient(create_app(sandbox_project / "asac.yaml", "fake"))
    body = json.dumps(
        {
            "webhookEvent": "jira:issue_created",
            "issue": {"key": "../x PAY", "fields": {"issuetype": {"name": "Story"}, "labels": ["asac-enabled"]}},  # noqa: E501
        }
    ).encode()  # fmt: skip
    assert post(client, body, sign(SECRET, body)).json()["runs"] == []


def test_delegate_step_runs_command_in_runner_and_audits_output(
    sandbox_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ASAC_FAKE_DELEGATE", "1")
    _delegate_project(sandbox_project, fallback=False)
    from asac.ports.runner import ExecResult

    runner = FakeRunner(results=[ExecResult(0, "did the work\n")])
    out, store = _run(sandbox_project, runner)
    assert runner.executed and runner.executed[0][0] == "claude"
    rows = [a for a in store.audit("r1") if a.action == "runner.output"]
    assert rows and rows[0].detail.startswith("exit=0 sha256=") and "did the work" in rows[0].detail
    assert int(out.code) in (0, 2)
    arts = FsArtifactStore(state_dir(sandbox_project) / "artifacts").list("r1")
    assert [a.name for a in arts] == ["development-output.txt"]


def test_delegate_failure_fails_step_and_keeps_run_resumable(
    sandbox_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ASAC_FAKE_DELEGATE", "1")
    _delegate_project(sandbox_project, fallback=False)
    from asac.ports.runner import ExecResult

    runner = FakeRunner(results=[ExecResult(1, "", "boom")])
    out, store = _run(sandbox_project, runner)
    assert int(out.code) == 1 and "exited with 1" in out.message
    assert runner.stopped  # the container is always stopped


def test_docker_runner_env_is_names_only_and_output_redacted(tmp_path: Path) -> None:
    r = DockerRunner(tmp_path, docker="docker", network="bridge", env={"API_KEY": "sk-secret-123"})
    cmd = r.command("r", "s")
    assert "API_KEY" in cmd and "sk-secret-123" not in " ".join(cmd)
    assert "bridge" in cmd
    assert r._redact("token sk-secret-123 ok") == "token [redacted] ok"
