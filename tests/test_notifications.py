"""The engine notifies on gates, blocks and failures, and never breaks because of it."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

import asac.engine.runtime as runtime
from asac.cli import app
from asac.ports.notifier import Notification, NotifyError

runner = CliRunner()


class Recorder:
    def __init__(self, fail: bool = False) -> None:
        self.sent: list[Notification] = []
        self.fail = fail

    def send(self, note: Notification) -> None:
        if self.fail:
            raise NotifyError("channel down")
        self.sent.append(note)


@pytest.fixture(autouse=True)
def fixed_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASAC_FIXED_TIME", "2026-01-01T00:00:00Z")


def apply(project: Path, rec: Recorder, monkeypatch: pytest.MonkeyPatch, run_id: str = "run1"):  # type: ignore[no-untyped-def]
    monkeypatch.setattr(runtime, "from_project", lambda values, env: rec)
    return runner.invoke(
        app,
        ["apply", "-p", "feature", "--harness", "fake", "--run-id", run_id,
         "-f", str(project / "asac.yaml")],
    )  # fmt: skip


def test_gate_opened_notifies_with_role(
    sandbox_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rec = Recorder()
    assert apply(sandbox_project, rec, monkeypatch).exit_code == 2
    (n,) = rec.sent
    assert n.kind == "gate.opened" and n.gate_id == "gate_run1_requirements"
    assert n.role == "product_owner" and n.run_id == "run1"


def test_failing_channel_does_not_change_the_run(
    sandbox_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert apply(sandbox_project, Recorder(fail=True), monkeypatch).exit_code == 2
    logs = runner.invoke(app, ["logs", "run1", "-f", str(sandbox_project / "asac.yaml")]).stdout
    assert "notify.failed" in logs and "channel down" in logs


def test_blocked_run_notifies(sandbox_project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rec = Recorder()
    assert apply(sandbox_project, rec, monkeypatch).exit_code == 2  # gate first
    f = str(sandbox_project / "asac.yaml")
    runner.invoke(app, ["approve", "gate_run1_requirements", "--role", "product_owner", "-f", f])
    monkeypatch.setenv("ASAC_FAKE_RESULT", json.dumps({"tokens": 3_000_000}))
    monkeypatch.setattr(runtime, "from_project", lambda values, env: rec)
    r = runner.invoke(app, ["apply", "--resume", "run1", "--harness", "fake", "-f", f])
    assert r.exit_code == 3
    assert "step.blocked" in {n.kind for n in rec.sent}


def test_project_targets_resolve_vault_references(monkeypatch: pytest.MonkeyPatch) -> None:
    from asac.adapters.notify import FanOut, SlackNotifier, from_project

    monkeypatch.setenv("ASAC_VAULT_NOTIFY_OPS", "slack+https://hooks.example/ops")
    notifier = from_project({"notify_targets": ["${vault.notify/ops}"]}, {})
    assert isinstance(notifier, FanOut)
    (target,) = notifier._targets
    assert isinstance(target, SlackNotifier)


def test_unresolvable_project_target_is_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    from asac.adapters.notify import from_project

    monkeypatch.delenv("ASAC_VAULT_NOTIFY_MISSING", raising=False)
    assert from_project({"notify_targets": ["${vault.notify/missing}"]}, {}) is None


def test_plain_url_in_vars_is_refused() -> None:
    from asac.adapters.notify import from_project

    # a URL is a secret: it must come from a vault reference, never from the vars file
    assert from_project({"notify_targets": ["slack+https://hooks.example/x"]}, {}) is None
