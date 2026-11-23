"""CLI paths not reached elsewhere: watch mode, portal and daemon start-up, error exits."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

import asac.cli as cli
from asac.cli import app

runner = CliRunner()


@pytest.fixture(autouse=True)
def fixed_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASAC_FIXED_TIME", "2026-01-01T00:00:00Z")


def run(project: Path, *args: str) -> Any:
    return runner.invoke(app, [*args, "-f", str(project / "asac.yaml")])


def test_watch_stops_at_a_gate_when_interrupted(
    sandbox_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import time

    def interrupt(_: float) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(time, "sleep", interrupt)
    r = run(sandbox_project, "apply", "-p", "feature", "--harness", "fake",
            "--run-id", "w1", "--watch", "--poll", "0")  # fmt: skip
    assert r.exit_code == 2
    assert "stopped watching" in r.output
    assert "w1" in run(sandbox_project, "status").output


def test_watch_resume_unknown_run_is_an_error(sandbox_project: Path) -> None:
    r = run(sandbox_project, "apply", "--harness", "fake", "--resume", "nope", "--watch")
    assert r.exit_code == 1 and "not found" in r.output


def test_reopen_needs_resume(sandbox_project: Path) -> None:
    r = run(sandbox_project, "apply", "--reopen")
    assert r.exit_code == 1 and "--reopen needs --resume" in r.output


def test_learn_unknown_run(sandbox_project: Path) -> None:
    r = run(sandbox_project, "learn", "nope")
    assert r.exit_code == 1 and "not found" in r.output


def test_learn_with_nothing_to_report(sandbox_project: Path) -> None:
    run(sandbox_project, "apply", "-p", "feature", "--harness", "fake", "--run-id", "l1")
    assert run(sandbox_project, "learn", "l1").exit_code == 0
    text = (sandbox_project / ".asac" / "proposals" / "l1.md").read_text()
    assert "Nothing to learn" in text or "Observations" in text


def test_bootstrap_errors(sandbox_project: Path) -> None:
    run(sandbox_project, "apply", "-p", "feature", "--harness", "fake", "--run-id", "b1")
    first = run(sandbox_project, "evidence", "bootstrap", "b1", "--evidence", "x", "--no-resume")
    assert first.exit_code == 0
    again = run(sandbox_project, "evidence", "bootstrap", "b1", "--evidence", "x", "--no-resume")
    assert again.exit_code == 1 and "error" in again.output
    ghost = run(sandbox_project, "evidence", "bootstrap", "ghost", "--evidence", "x")
    assert ghost.exit_code == 1


def test_portal_refuses_without_sso_or_dev(
    sandbox_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("ASAC_OIDC_ISSUER", raising=False)
    monkeypatch.delenv("ASAC_ENV", raising=False)
    r = runner.invoke(app, ["portal"])
    assert r.exit_code == 1 and "ASAC_OIDC_ISSUER" in r.output


def test_portal_needs_every_oidc_variable(
    sandbox_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ASAC_OIDC_ISSUER", "https://idp.example")
    monkeypatch.delenv("ASAC_OIDC_CLIENT_ID", raising=False)
    r = runner.invoke(app, ["portal"])
    assert r.exit_code == 1 and "ASAC_OIDC_CLIENT_ID" in r.output


def test_portal_starts_in_dev_mode(sandbox_project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    served: dict[str, Any] = {}
    monkeypatch.setattr(
        cli, "_serve", lambda a, host, port: served.update(app=a, host=host, port=port)
    )
    monkeypatch.setenv("ASAC_ENV", "dev")
    monkeypatch.delenv("ASAC_OIDC_ISSUER", raising=False)
    r = runner.invoke(
        app, ["portal", "--port", "9999", "--data", str(sandbox_project.parent / "pd")]
    )
    assert r.exit_code == 0
    assert served["host"] == "127.0.0.1" and served["port"] == 9999
    from fastapi.testclient import TestClient

    c = TestClient(served["app"])
    assert c.get("/healthz").json() == {"status": "ok"}
    assert c.get("/api/v1/login-options").json()["mode"] == "dev"


def test_daemon_needs_secret_then_starts(
    sandbox_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("ASAC_WEBHOOK_SECRET", raising=False)
    r = run(sandbox_project, "daemon")
    assert r.exit_code == 1 and "ASAC_WEBHOOK_SECRET" in r.output
    served: dict[str, Any] = {}
    monkeypatch.setattr(cli, "_serve", lambda a, host, port: served.update(port=port))
    monkeypatch.setenv("ASAC_WEBHOOK_SECRET", "x")
    assert run(sandbox_project, "daemon", "--port", "9001").exit_code == 0
    assert served["port"] == 9001


def test_serve_hands_the_app_to_uvicorn(monkeypatch: pytest.MonkeyPatch) -> None:
    import uvicorn

    got: dict[str, Any] = {}
    monkeypatch.setattr(uvicorn, "run", lambda a, **kw: got.update(kw))
    cli._serve(object(), "127.0.0.1", 1234)
    assert got["port"] == 1234 and got["host"] == "127.0.0.1"


def test_evidence_verify_flags_a_missing_requirement(sandbox_project: Path) -> None:
    run(sandbox_project, "apply", "-p", "feature", "--harness", "fake", "--run-id", "v1")
    from asac.engine.runtime import store_for

    store = store_for(sandbox_project / "asac.yaml")
    store.set_step_status("v1", "development", "completed")  # claims done, evidence never recorded
    r = run(sandbox_project, "evidence", "verify", "v1")
    assert r.exit_code == 1 and "missing: development requires" in r.output


def test_project_commands(tmp_path: Path) -> None:
    manifest = tmp_path / "asac.yaml"
    manifest.write_text("x: 1\n", encoding="utf-8")
    data = str(tmp_path / "data")
    r = runner.invoke(app, ["project", "add", "pay", str(manifest), "--data", data, "--team", "T"])
    assert r.exit_code == 0, r.output
    again = runner.invoke(app, ["project", "add", "pay", str(manifest), "--data", data])
    assert again.exit_code == 1 and "already exists" in again.output
    assert (
        runner.invoke(app, ["project", "add", "Bad Id", str(manifest), "--data", data]).exit_code
        == 1
    )
    missing = runner.invoke(
        app, ["project", "add", "p2", str(tmp_path / "no.yaml"), "--data", data]
    )
    assert missing.exit_code == 1
    assert "pay" in runner.invoke(app, ["project", "list", "--data", data]).output
    assert runner.invoke(app, ["project", "archive", "pay", "--data", data]).exit_code == 0
    assert "pay" not in runner.invoke(app, ["project", "list", "--data", data]).output
    listed = runner.invoke(app, ["project", "list", "--archived", "--data", data]).output
    assert "archived" in listed
    assert (
        runner.invoke(app, ["project", "archive", "pay", "--restore", "--data", data]).exit_code
        == 0
    )
    assert runner.invoke(app, ["project", "archive", "nope", "--data", data]).exit_code == 1


def test_the_audit_text_view_shows_the_detail_of_a_security_event(sandbox_project: Path) -> None:
    from asac.engine.runtime import store_for

    store = store_for(sandbox_project / "asac.yaml")
    store.create_run("v1", "feature", "2026-01-01T00:00:00Z")
    store.append_audit("v1", "cli", "sandbox.denied", "2026-01-01T00:00:00Z", "s",
                       "filesystem /home/me/.ssh/id_rsa")  # fmt: skip
    store.append_audit("v1", "cli", "step.started", "2026-01-01T00:00:00Z", "s", "analyst")
    out = run(sandbox_project, "audit", "--run-id", "v1").stdout
    denied = next(ln for ln in out.splitlines() if "sandbox.denied" in ln)
    started = next(ln for ln in out.splitlines() if "step.started" in ln)
    assert "filesystem /home/me/.ssh/id_rsa" in denied
    assert "analyst" not in started  # ordinary events keep their short line
