"""A rejection sends the reason back to the agent, up to a cap. The cap is never exceeded."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from asac.cli import app
from tests.conftest import init_git

runner = CliRunner()
EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "real-tools"


def asac(root: Path, *args: str):  # type: ignore[no-untyped-def]
    return runner.invoke(app, [*args, "-f", str(root / "asac.yaml")])


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    import shutil

    root = tmp_path / "proj"
    shutil.copytree(EXAMPLE, root)
    shutil.copy(root / "vars" / "claude-code.yaml", root / "asac.vars.yaml")
    init_git(root)
    bindir = tmp_path / "bin"
    bindir.mkdir()
    counter = tmp_path / "launches.txt"
    tool = bindir / "claude"
    # Each launch appends its prompt. It writes a spec only once the prompt carries feedback.
    # A real agent writes a spec that passes the hook on the first try, so the gate opens. It
    # changes only when the reviewer's rejection is in its prompt.
    tool.write_text(
        "#!/bin/sh\n"
        f'printf "%s\\n---\\n" "$2" >> "{tmp_path / "prompts.txt"}"\n'
        f'echo x >> "{counter}"\n'
        'if echo "$2" | grep -q "Rejected by the reviewer"; then\n'
        '  printf "# Spec\\n## Acceptance criteria\\n- revised\\n" > SPEC.md\n'
        "else\n"
        '  printf "# Spec\\n## Acceptance criteria\\n- first try\\n" > SPEC.md\n'
        "fi\n"
        'echo \'{"type":"result","is_error":false,"total_cost_usd":0.01,'
        '"usage":{},"result":"x"}\'\n'
    )
    tool.chmod(0o755)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("ASAC_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("ASAC_FIXED_TIME", "2026-01-01T00:00:00Z")
    monkeypatch.setenv("ASAC_AUTORUN", "1")
    monkeypatch.setenv("ASAC_SANDBOX", "0")
    monkeypatch.setenv("PATH", f"{bindir}:/usr/bin:/bin")
    return root


def _launches(tmp_path: Path) -> int:
    f = tmp_path / "launches.txt"
    return f.read_text().count("x") if f.exists() else 0


def test_a_rejection_relaunches_the_agent_with_the_reason(project: Path, tmp_path: Path) -> None:
    asac(project, "apply", "-p", "feature", "--run-id", "r1")
    assert _launches(tmp_path) == 1
    asac(project, "approve", "gate_r1_requirements", "--role", "product_owner", "--by", "po",
         "--reject", "--comment", "REJECTED-REASON: criteria are vague")  # fmt: skip
    r = asac(project, "apply", "--resume", "r1")
    assert _launches(tmp_path) == 2, r.output  # the agent was launched again, by ASAC
    prompts = (tmp_path / "prompts.txt").read_text()
    assert "criteria are vague" in prompts.split("---")[-2]  # the reason is in the new prompt
    assert "gate_r1_requirements is pending" in r.output  # the revised spec goes to the gate again


def test_the_rejected_attempt_and_its_reason_stay_in_the_audit(
    project: Path, tmp_path: Path
) -> None:
    asac(project, "apply", "-p", "feature", "--run-id", "r2")
    asac(project, "approve", "gate_r2_requirements", "--role", "product_owner", "--by", "po",
         "--reject", "--comment", "REJECTED-REASON: too vague", "--no-resume")  # fmt: skip
    asac(project, "apply", "--resume", "r2")
    log = asac(project, "logs", "r2").output
    assert "gate.rejected requirements" in log and "too vague" in log
    assert "rejection.handled requirements" in log


def test_the_retries_are_capped_then_the_run_fails(project: Path, tmp_path: Path) -> None:
    """A human who rejects again and again must not create an endless loop."""
    asac(project, "apply", "-p", "feature", "--run-id", "r3")
    for n in range(1, 4):
        asac(project, "approve", "gate_r3_requirements", "--role", "product_owner", "--by", "po",
             "--reject", "--comment", f"no {n}", "--no-resume")  # fmt: skip
        r = asac(project, "apply", "--resume", "r3")
    # the cap ends the retries: the run is no longer waiting for a decision, and nothing is
    # launched again after the cap
    assert "failed at requirements" in r.output or "blocked at requirements" in r.output, r.output
    assert _launches(tmp_path) <= 3  # first run + at most two relaunches; the cap stops the rest


@pytest.mark.xfail(
    strict=True,
    reason="decision pending (SCOPE in the report): without autorun the reason is not yet put "
    "in the brief the person reads, and resume blocks on a hook before the person can act",
)
def test_without_autorun_a_rejection_hands_the_step_back_to_a_person(
    project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ASAC_AUTORUN", "0")
    asac(project, "apply", "-p", "feature", "--harness", "claude-code", "--run-id", "r4")
    asac(project, "approve", "gate_r4_requirements", "--role", "product_owner", "--by", "po",
         "--reject", "--comment", "REJECTED-REASON: x", "--no-resume")  # fmt: skip
    r = asac(project, "apply", "--resume", "r4")
    # assist without autorun: the step waits for the person to record the evidence again
    assert "waiting for evidence" in r.output or "handed to a person" in r.output, r.output
    feedback = Path(os.environ["ASAC_STATE_DIR"]) / "briefs" / "r4" / "requirements.feedback.md"
    assert "REJECTED-REASON" in feedback.read_text()


@pytest.mark.xfail(
    strict=True,
    reason="a relaunch blocked by a hook is currently retried on the next resume; whether it "
    "should wait for a person is a design decision, not yet taken",
)
def test_a_relaunch_that_is_blocked_by_a_hook_asks_the_person_again(
    project: Path, tmp_path: Path
) -> None:
    """A blocked relaunch never reaches a gate, so there is nothing to reject. The run waits
    for the person's next decision: the reviewer is not bypassed, and nothing is relaunched by
    itself after a hook failure."""
    tool = Path(os.environ["PATH"].split(":")[0]) / "claude"
    tool.write_text(
        "#!/bin/sh\n"
        f'echo x >> "{tmp_path / "launches.txt"}"\n'
        'echo \'{"type":"result","is_error":false,"total_cost_usd":0.01,'
        '"usage":{},"result":"x"}\'\n'
    )  # never writes SPEC.md: the step-scope hook blocks every attempt
    asac(project, "apply", "-p", "feature", "--run-id", "b1")
    before = _launches(tmp_path)
    r = asac(project, "apply", "--resume", "b1")
    assert _launches(tmp_path) == before, "a blocked step was relaunched without a decision"
    assert "blocked" in asac(project, "status").output
    assert r.exit_code in (0, 3)


def test_the_rejection_cap_is_on_rejections_not_on_hook_failures(
    project: Path, tmp_path: Path
) -> None:
    """Two rejections with a reason: two relaunches. The third rejection ends the run."""
    asac(project, "apply", "-p", "feature", "--run-id", "c1")
    outcomes = []
    for n in range(1, 4):
        asac(project, "approve", "gate_c1_requirements", "--role", "product_owner", "--by", "po",
             "--reject", "--comment", f"REJECTED-REASON: no {n}", "--no-resume")  # fmt: skip
        r = asac(project, "apply", "--resume", "c1")
        outcomes.append(r.output)
    assert "waiting for gate" in outcomes[0] and "rejected" not in outcomes[0]
    assert "failed at requirements" in outcomes[2], outcomes[2]
    assert _launches(tmp_path) == 3  # the first run + two relaunches, never a fourth


@pytest.mark.xfail(
    strict=True,
    reason="defect, confirmed: a resume of a failed run relaunches the step and reopens its "
    "rejected gate with no decision. The broad fix (failed steps are terminal) breaks escalation "
    "and policy paths; a narrow fix is needed first",
)
def test_resuming_a_failed_run_never_reopens_a_rejected_gate(project: Path, tmp_path: Path) -> None:
    """A run that failed after its rejections is finished. A resume must not reopen its gate
    and relaunch the agent: only an explicit --reopen by a person may do that."""
    asac(project, "apply", "-p", "feature", "--run-id", "f1")
    for n in range(1, 4):  # the third rejection exhausts the cap and fails the run
        asac(project, "approve", "gate_f1_requirements", "--role", "product_owner", "--by", "po",
             "--reject", "--comment", f"REJECTED-REASON: {n}", "--no-resume")  # fmt: skip
        asac(project, "apply", "--resume", "f1")
    assert "failed" in asac(project, "status").output
    launches = _launches(tmp_path)
    r = asac(project, "apply", "--resume", "f1")
    assert _launches(tmp_path) == launches, "a failed run was relaunched without a decision"
    assert "gate_waiting" not in asac(project, "status").output
    assert "failed" in asac(project, "status").output, r.output
    assert asac(project, "gates").output.count("pending") == 0


def test_a_step_waiting_for_evidence_moves_on_when_the_evidence_arrives(
    project: Path, tmp_path: Path
) -> None:
    """The one legitimate resume: the person supplies the evidence the step waits for, then the
    run continues to the next gate. Nothing is relaunched without that evidence."""
    asac(project, "apply", "-p", "feature", "--run-id", "ev1")
    before = _launches(tmp_path)
    asac(project, "evidence", "bootstrap", "ev1", "--evidence", "spec_reviewed", "--no-resume")
    asac(project, "approve", "gate_ev1_requirements", "--role", "product_owner", "--by", "po",
         "--no-resume")  # fmt: skip
    r = asac(project, "apply", "--resume", "ev1")
    assert "gate_ev1_development" in r.output, r.output  # moved on to the next gate
    assert _launches(tmp_path) >= before  # the agent may run for the next step only
