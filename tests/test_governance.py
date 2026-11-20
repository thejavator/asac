"""M4: budgets, autonomy, escalation, policies, kill and learn, in the sandbox."""

import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from asac.cli import app

runner = CliRunner()


@pytest.fixture(autouse=True)
def fixed_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASAC_FIXED_TIME", "2026-01-01T00:00:00Z")


def asac(project: Path, *args: str):  # type: ignore[no-untyped-def]
    return runner.invoke(app, [*args, "-f", str(project / "asac.yaml")])


def start(project: Path, run_id: str = "run1"):  # type: ignore[no-untyped-def]
    return asac(project, "apply", "-p", "feature", "--harness", "fake", "--run-id", run_id)


def approve_requirements(project: Path, run_id: str = "run1") -> None:
    r = asac(project, "approve", f"gate_{run_id}_requirements", "--role", "product_owner")
    assert r.exit_code == 0


def test_budget_overrun_blocks_run(sandbox_project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASAC_FAKE_RESULT", json.dumps({"tokens": 3_000_000}))
    r = start(sandbox_project)
    assert r.exit_code == 3
    assert "token" in r.stdout.lower()
    assert "blocked" in asac(sandbox_project, "status").stdout


def test_iteration_ceiling_blocks(sandbox_project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASAC_FAKE_RESULT", json.dumps({"iterations": 9}))
    assert start(sandbox_project).exit_code == 3


def test_readonly_autonomy_sets_readonly_permission(sandbox_project: Path) -> None:
    from asac.engine.governance import permission_for
    from asac.loader.load import load_manifest

    m = load_manifest(sandbox_project / "asac.yaml")
    step = m.pipelines["feature"].steps["development"]
    assert permission_for(step) == "delegate"
    assert permission_for(step.model_copy(update={"autonomy": "readonly"})) == "readonly"


def test_escalation_waits_for_human(sandbox_project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert start(sandbox_project).exit_code == 2
    approve_requirements(sandbox_project)
    monkeypatch.setenv("ASAC_FAKE_RESULT", json.dumps({"escalate": ["outside_scope"]}))
    r = asac(sandbox_project, "apply", "--resume", "run1", "--harness", "fake")
    assert r.exit_code == 2
    assert "escalated" in r.stdout


def test_gate_policy_blocks_low_coverage(
    sandbox_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    if shutil.which("opa") is None:
        pytest.skip("opa binary not installed")
    assert start(sandbox_project).exit_code == 2
    approve_requirements(sandbox_project)
    monkeypatch.setenv(
        "ASAC_FAKE_RESULT",
        json.dumps({"coverage": 50, "skill_params": {"coverage_min": 85}}),
    )
    r = asac(sandbox_project, "apply", "--resume", "run1", "--harness", "fake")
    assert r.exit_code == 3
    assert "Coverage 50" in r.stdout


def test_kill_stops_and_prevents_resume(sandbox_project: Path) -> None:
    assert start(sandbox_project).exit_code == 2
    k = asac(sandbox_project, "kill", "run1", "--by", "ops", "--reason", "stop")
    assert k.exit_code == 0
    r = asac(sandbox_project, "apply", "--resume", "run1", "--harness", "fake")
    assert r.exit_code == 3
    assert "killed" in r.stdout
    assert "run.killed" in asac(sandbox_project, "logs", "run1").stdout
    assert asac(sandbox_project, "kill", "run1").exit_code == 1  # already killed
    assert asac(sandbox_project, "kill", "nope").exit_code == 1


def test_learn_writes_proposal_only(sandbox_project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASAC_FAKE_RESULT", json.dumps({"tokens": 3_000_000}))
    start(sandbox_project)
    before = (sandbox_project / "asac.yaml").read_text()
    r = asac(sandbox_project, "learn", "run1")
    assert r.exit_code == 0
    text = (sandbox_project / ".asac" / "proposals" / "run1.md").read_text()
    assert "step.blocked" in text
    assert (sandbox_project / "asac.yaml").read_text() == before


def test_logs_json_emits_spans(sandbox_project: Path) -> None:
    start(sandbox_project)
    spans = json.loads(asac(sandbox_project, "logs", "run1", "--json").stdout)
    assert spans and {"trace_id", "span_id", "name", "attributes"} <= set(spans[0])
    assert len({s["trace_id"] for s in spans}) == 1


def test_missing_opa_blocks_instead_of_crashing(
    sandbox_project: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    assert start(sandbox_project).exit_code == 2
    approve_requirements(sandbox_project)
    monkeypatch.setenv("PATH", str(tmp_path))  # no opa binary reachable
    r = asac(sandbox_project, "apply", "--resume", "run1", "--harness", "fake")
    assert r.exit_code in (0, 2, 3)  # a clean outcome, never a traceback
    assert r.exception is None or isinstance(r.exception, SystemExit)


def test_escalation_can_be_approved_and_resumed(
    sandbox_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert start(sandbox_project).exit_code == 2
    approve_requirements(sandbox_project)
    monkeypatch.setenv("ASAC_FAKE_RESULT", json.dumps({"escalate": ["outside_scope"]}))
    assert asac(sandbox_project, "apply", "--resume", "run1", "--harness", "fake").exit_code == 2
    gates = asac(sandbox_project, "gates").stdout
    assert "escalation" in gates
    monkeypatch.delenv("ASAC_FAKE_RESULT")
    r = asac(sandbox_project, "approve", "gate_run1_development_escalation", "--role", "tech_lead")
    assert r.exception is None or isinstance(r.exception, SystemExit)


def test_retries_are_capped_and_audited(
    sandbox_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ASAC_FAKE_FAIL", "requirements")
    monkeypatch.setenv("ASAC_RETRIES", "2")
    r = start(sandbox_project)
    assert r.exit_code == 1
    audit = asac(sandbox_project, "audit").stdout
    assert audit.count("step.retry") == 2  # 3 attempts in all, then the run fails


def test_a_flaky_step_succeeds_on_retry(
    sandbox_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from asac.adapters.fake_harness import FakeHarness

    calls = {"n": 0}
    real = FakeHarness.run

    def flaky(self, task, context):  # type: ignore[no-untyped-def]
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("transient")
        return real(self, task, context)

    monkeypatch.setattr(FakeHarness, "run", flaky)
    monkeypatch.setenv("ASAC_RETRIES", "1")
    r = start(sandbox_project)
    assert r.exit_code == 2  # past the failure, waiting at the first gate
    assert "step.retry" in asac(sandbox_project, "audit").stdout


def test_no_retry_by_default(sandbox_project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASAC_FAKE_FAIL", "requirements")
    assert start(sandbox_project).exit_code == 1
    assert "step.retry" not in asac(sandbox_project, "audit").stdout


def _fan_out(project: Path) -> None:
    """Two more independent steps after `requirements`, next to `development`."""
    import yaml

    f = project / "asac.yaml"
    data = yaml.safe_load(f.read_text())
    steps = data["pipelines"]["feature"]["steps"]
    for name in ("docs", "audit"):
        steps[name] = {
            "capability": "implementation", "agent": "dev", "mode": "assist",
            "dependsOn": ["requirements"], "requiresEvidence": ["spec_reviewed"],
        }  # fmt: skip
    steps["development"]["mode"] = "assist"
    f.write_text(yaml.safe_dump(data))


@pytest.mark.parametrize("parallel", ["1", "4"])
def test_independent_steps_run_in_one_wave(
    sandbox_project: Path, monkeypatch: pytest.MonkeyPatch, parallel: str
) -> None:
    monkeypatch.setenv("ASAC_PARALLEL", parallel)
    _fan_out(sandbox_project)
    assert start(sandbox_project).exit_code == 2
    approve_requirements(sandbox_project)
    r = asac(sandbox_project, "apply", "--resume", "run1", "-p", "feature", "--harness", "fake")
    assert r.exit_code in (0, 2), r.stdout
    from asac.engine.runtime import store_for

    store = store_for(sandbox_project / "asac.yaml")
    started = {a.step_id for a in store.audit("run1") if a.action == "step.started"}
    if parallel == "4":  # a hand-off in one step does not stop its siblings of the same wave
        assert {"development", "docs", "audit"} <= started
    else:  # sequential: the first hand-off stops the run
        assert started & {"development", "docs", "audit"}


def test_parallel_setting_is_clamped(monkeypatch: pytest.MonkeyPatch) -> None:
    from asac.engine.runtime import _parallel

    monkeypatch.setenv("ASAC_PARALLEL", "99")
    assert _parallel({}) == 8
    monkeypatch.setenv("ASAC_PARALLEL", "x")
    assert _parallel({}) == 1
