"""F57: a `mode: delegate` step runs the agent in the runner, and the engine treats it like an
automatic one: it books the cost, loops on a failing check, relaunches after a rejection, checks
the integrity of the rules around the run, then commits and opens the gate.

The runner here is a stand-in that runs the command on the host (a shell script playing `claude`),
so the engine's side is checked without Docker. The real container is `test_delegate_real.py`.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from asac.adapters.runner_local import FakeRunner
from asac.cli import app
from asac.ports.runner import ExecResult

MINI = """\
asac: { spec: "0.4", workspace: del, team: t }
providers:
  llm: { source: asac/claude, version: "~> 1.0", config: { model: m } }
capabilities:
  build: { description: Build it, evidence: [built] }
evidenceTypes:
  built: { description: Built }
skills:
  impl: { ref: .asac/skills/impl.md, fulfils: build }
agents:
  dev: { skill: impl, provider: llm, harness: claude-code }
hooks:
  definitions:
    probe: { run: .asac/hooks/probe.sh, on_fail: block }
pipelines:
  feature:
    steps:
      build:
        capability: build
        agent: dev
        mode: delegate
        execution: { runner: docker }
        producesEvidence: [built]
        loop: { until: [probe], max_iterations: 4 }
        gate: { type: human, role: product_owner, timeout: 24h }
"""
PROBE = (
    '#!/bin/sh\ntest -f "$ASAC_WORKTREE/done.txt" || { echo "done.txt is missing" >&2; exit 1; }\n'
)
REPORT = {"type": "result", "is_error": False, "total_cost_usd": 0.0421,
          "usage": {"input_tokens": 100, "output_tokens": 20}, "result": "ok"}  # fmt: skip


class HostRunner(FakeRunner):
    """Runs the delegated command on the host, in the run's worktree, as a stand-in for Docker.

    ``script`` plays the agent: it gets the prompt as $2 (like ``claude -p <prompt>``).
    """

    def __init__(self, worktree: Path, script: str) -> None:
        super().__init__()
        self.worktree, self.script, self.launches = worktree, script, 0

    def exec(self, handle: str, argv: list[str], timeout: int) -> ExecResult:
        self.launches += 1
        self.executed.append(list(argv))
        done = subprocess.run(
            ["sh", "-c", self.script, "agent", *argv[1:]],
            cwd=self.worktree, capture_output=True, text=True, timeout=30,
        )  # fmt: skip
        return ExecResult(done.returncode, done.stdout, done.stderr)


def _git(root: Path, *args: str) -> None:
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}  # fmt: skip
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, env=env)


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "proj"
    (root / ".asac" / "skills").mkdir(parents=True)
    (root / ".asac" / "hooks").mkdir(parents=True)
    (root / ".asac" / "skills" / "impl.md").write_text("Create done.txt.\n")
    (root / ".asac" / "hooks" / "probe.sh").write_text(PROBE)
    (root / ".asac" / "hooks" / "probe.sh").chmod(0o755)
    (root / "asac.yaml").write_text(MINI)
    _git(root, "init", "-q", "-b", "main")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "base")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("ASAC_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("ASAC_FIXED_TIME", "2026-01-01T00:00:00Z")
    monkeypatch.setenv("ASAC_AUTORUN", "0")  # delegation is not autorun: it must work without it
    monkeypatch.setenv("ASAC_SANDBOX", "0")
    return root


def _agent(fix_from_launch: int, cost: float | None = 0.0421, extra: str = "") -> str:
    """A stand-in agent: creates done.txt from its Nth launch if the prompt carries the reason."""
    body = {**REPORT, "total_cost_usd": cost}
    if cost is None:
        body.pop("total_cost_usd")
    report = json.dumps(body)
    return (
        "n=$(cat .launches 2>/dev/null | wc -l); echo x >> .launches; n=$((n+1))\n"
        f'if [ "$n" -ge {fix_from_launch} ]; then echo ok > done.txt; fi\n{extra}\n'
        f"echo '{report}'\n"
    )


def _drive(project: Path, runner: HostRunner | None, *args: str):  # type: ignore[no-untyped-def]
    from asac.engine import runtime

    real = runtime.runner_from_vars
    if runner is not None:
        runtime.runner_from_vars = lambda root, values, wt=None: runner  # type: ignore[assignment]
    try:
        return CliRunner().invoke(app, [*args, "-f", str(project / "asac.yaml")])
    finally:
        runtime.runner_from_vars = real  # type: ignore[assignment]


def _wt(run_id: str) -> Path:
    return Path(os.environ["ASAC_STATE_DIR"]) / "worktrees" / run_id


def _log(project: Path, run_id: str) -> str:
    return _drive(project, None, "logs", run_id).output


def test_the_cost_in_the_agents_report_is_booked(project: Path) -> None:
    """F57.2: `spend.recorded` carries the cost the tool reported, not zero."""
    runner = HostRunner(_wt("d1"), _agent(fix_from_launch=1))
    _drive(project, runner, "apply", "-p", "feature", "--harness", "claude-code", "--run-id", "d1")
    log = _log(project, "d1")
    assert "spend.recorded build  tokens=120 cost_usd=0.0421" in log
    assert "cost=unknown" not in log


def test_a_report_without_a_cost_is_unknown_never_zero(project: Path) -> None:
    runner = HostRunner(_wt("d2"), _agent(fix_from_launch=1, cost=None))
    _drive(project, runner, "apply", "-p", "feature", "--harness", "claude-code", "--run-id", "d2")
    assert "cost=unknown" in _log(project, "d2")


def test_an_output_with_no_report_at_all_is_an_unknown_cost(project: Path) -> None:
    """The tool printed no JSON (a crash after the work, a wrapper): the cost cannot be known."""
    runner = HostRunner(_wt("d2b"), "echo ok > done.txt\necho 'finished, no report'\n")
    _drive(project, runner, "apply", "-p", "feature", "--harness", "claude-code", "--run-id", "d2b")
    log = _log(project, "d2b")
    spend = next(x for x in log.splitlines() if "spend.recorded" in x)
    assert "cost=unknown" in spend and "cost_usd=0.0000 cost=unknown" in spend


def test_a_report_that_says_error_fails_the_step(project: Path) -> None:
    """The tool exited 0 but its own report says it failed."""
    bad = json.dumps({**REPORT, "is_error": True})
    runner = HostRunner(_wt("d2c"), f"echo ok > done.txt\necho '{bad}'\n")
    r = _drive(project, runner, "apply", "-p", "feature", "--harness", "claude-code",
               "--run-id", "d2c")  # fmt: skip
    assert r.exit_code == 1 and "reported an error" in _log(project, "d2c")


def test_the_cost_counts_against_a_cost_budget(project: Path) -> None:
    """F57.2: the budget sees the spend of a delegated step (R20: unknown cost blocks it)."""
    (project / "asac.yaml").write_text(
        MINI.replace("hooks:", "budgets: { per_run: { cost_usd: 0.01 } }\nhooks:", 1)
    )
    _git(project, "add", "-A")
    _git(project, "commit", "-q", "-m", "budget")
    runner = HostRunner(_wt("d3"), _agent(fix_from_launch=1))  # costs 0.0421 > 0.01
    r = _drive(project, runner, "apply", "-p", "feature", "--harness", "claude-code",
               "--run-id", "d3")  # fmt: skip
    assert r.exit_code == 3, r.output
    assert "budget" in _log(project, "d3")


def test_a_failing_check_relaunches_the_agent_in_the_runner_with_the_reason(project: Path) -> None:
    """F57.3: the loop works with no person between turns, and the agent is sent the error.

    The stand-in agent only fixes the work when its prompt carries the check's output, so a run
    that relaunches the agent without the reason cannot pass.
    """
    script = (
        "echo x >> .launches\n"
        'if echo "$2" | grep -q "done.txt is missing"; then echo ok > done.txt; fi\n'
        "echo '" + json.dumps(REPORT) + "'\n"
    )
    runner = HostRunner(_wt("d4"), script)
    r = _drive(project, runner, "apply", "-p", "feature", "--harness", "claude-code",
               "--run-id", "d4")  # fmt: skip
    log = _log(project, "d4")
    assert runner.launches == 2, (runner.launches, r.output, log)  # 1st: no reason, 2nd: fixed
    assert "step.iteration build  1 of 4 failed: probe: done.txt is missing" in log
    assert "step.iteration build  2 of 4 passed" in log
    assert "gate.opened build" in log


def test_without_the_reason_in_the_prompt_the_loop_would_not_converge(project: Path) -> None:
    """The control for the test above: an agent that ignores the prompt never gets past the cap."""
    runner = HostRunner(_wt("d4b"), _agent(fix_from_launch=99))
    _drive(project, runner, "apply", "-p", "feature", "--harness", "claude-code", "--run-id", "d4b")
    assert "gate.opened" not in _log(project, "d4b")


def test_a_check_that_never_passes_stops_at_the_cap(project: Path) -> None:
    runner = HostRunner(_wt("d5"), _agent(fix_from_launch=99))
    r = _drive(project, runner, "apply", "-p", "feature", "--harness", "claude-code",
               "--run-id", "d5")  # fmt: skip
    assert runner.launches == 4  # max_iterations
    assert r.exit_code == 1 and "loop cap reached" in _log(project, "d5")


def test_the_step_is_committed_and_the_gate_is_bound_to_that_commit(project: Path) -> None:
    """F57.6."""
    runner = HostRunner(_wt("d6"), _agent(fix_from_launch=1))
    r = _drive(project, runner, "apply", "-p", "feature", "--harness", "claude-code",
               "--run-id", "d6")  # fmt: skip
    assert r.exit_code == 2, r.output
    log = _log(project, "d6")
    sha = next(x for x in log.split() if len(x) == 40 and set(x) <= set("0123456789abcdef"))
    gates = _drive(project, None, "gates").output
    assert sha[:12] in gates
    shown = subprocess.run(["git", "show", "--name-only", "--format=", sha], cwd=_wt("d6"),
                           capture_output=True, text=True).stdout  # fmt: skip
    assert "done.txt" in shown


def test_a_rejection_relaunches_the_agent_in_the_runner(project: Path) -> None:
    """F57.4 and F23: a reasoned rejection sends the agent back, capped, with no autorun."""
    runner = HostRunner(_wt("d7"), _agent(fix_from_launch=1))
    _drive(project, runner, "apply", "-p", "feature", "--harness", "claude-code", "--run-id", "d7")
    before = runner.launches
    _drive(project, runner, "approve", "gate_d7_build", "--role", "product_owner", "--by", "po",
           "--reject", "--comment", "criteria are vague", "--no-resume")  # fmt: skip
    _drive(project, runner, "apply", "--resume", "d7", "--harness", "claude-code")
    log = _log(project, "d7")
    assert runner.launches == before + 1
    assert "rejection.handled build" in log and "attempt.after_rejection build" in log


def test_a_rejection_relaunch_is_capped(project: Path) -> None:
    from asac.engine.apply import rejection_cap
    from asac.loader.load import load_manifest

    cap = rejection_cap(load_manifest(project / "asac.yaml").pipelines["feature"].steps["build"])
    runner = HostRunner(_wt("d8"), _agent(fix_from_launch=1))
    _drive(project, runner, "apply", "-p", "feature", "--harness", "claude-code", "--run-id", "d8")
    for _ in range(cap + 2):
        _drive(project, runner, "approve", "gate_d8_build", "--role", "product_owner", "--by",
               "po", "--reject", "--comment", "no", "--no-resume")  # fmt: skip
        _drive(project, runner, "apply", "--resume", "d8", "--harness", "claude-code")
    assert _log(project, "d8").count("rejection.handled") == cap  # never more than the cap


def test_integrity_is_checked_around_the_delegated_run(project: Path) -> None:
    """F57.5: the rules are fingerprinted before and after, and a change blocks the step."""
    intact = HostRunner(_wt("d9"), _agent(fix_from_launch=1))
    _drive(project, intact, "apply", "-p", "feature", "--harness", "claude-code", "--run-id", "d9")
    assert "integrity.verified build" in _log(project, "d9")
    tamper = HostRunner(
        _wt("d10"), _agent(fix_from_launch=1, extra=f'echo "# hacked" >> "{project}/asac.yaml"')
    )  # an agent that reached the main checkout (a mount mistake, or no sandbox)
    r = _drive(project, tamper, "apply", "-p", "feature", "--harness", "claude-code",
               "--run-id", "d10")  # fmt: skip
    assert r.exit_code == 3, r.output
    log = _log(project, "d10")
    assert "integrity.violated build" in log and "asac.yaml" in log


def test_the_runner_events_and_the_full_output_are_recorded(project: Path) -> None:
    """F57.8."""
    runner = HostRunner(_wt("d11"), _agent(fix_from_launch=1))
    _drive(project, runner, "apply", "-p", "feature", "--harness", "claude-code", "--run-id", "d11")
    log = _log(project, "d11")
    for event in ("runner.started build", "runner.output build", "runner.stopped build"):
        assert event in log, event
    assert "sha256=" in next(x for x in log.splitlines() if "runner.output" in x)
    assert "artifact.stored build  build-output.txt" in log


def test_runner_started_records_the_network_the_container_is_on(project: Path) -> None:
    """F60.3: a reader of the audit can tell whether the container could reach anything."""
    isolated = HostRunner(_wt("d13"), _agent(fix_from_launch=1))
    isolated.network = "none"  # type: ignore[attr-defined]
    _drive(project, isolated, "apply", "-p", "feature", "--harness", "claude-code",
           "--run-id", "d13")  # fmt: skip
    started = next(x for x in _log(project, "d13").splitlines() if "runner.started" in x)
    assert started.endswith("network=none"), started
    egress = HostRunner(_wt("d14"), _agent(fix_from_launch=1))
    egress.network = "asac-egress"  # type: ignore[attr-defined]
    _drive(project, egress, "apply", "-p", "feature", "--harness", "claude-code",
           "--run-id", "d14")  # fmt: skip
    started = next(x for x in _log(project, "d14").splitlines() if "runner.started" in x)
    assert started.endswith("network=asac-egress"), started


def test_a_runner_that_is_down_hands_the_step_to_a_person(project: Path) -> None:
    """F57.7."""
    (project / "asac.yaml").write_text(
        MINI.replace(
            "execution: { runner: docker }", "execution: { runner: docker, fallback: assist }"
        )
    )
    _git(project, "add", "-A")
    _git(project, "commit", "-q", "-m", "fallback")
    down = HostRunner(_wt("d12"), _agent(fix_from_launch=1))
    down.up = False
    r = _drive(
        project, down, "apply", "-p", "feature", "--harness", "claude-code", "--run-id", "d12"
    )
    assert r.exit_code == 2 and "runner.unavailable build" in _log(project, "d12")
    assert down.launches == 0


def test_the_loop_cap_is_a_hard_cap_even_when_incident_retries_are_on(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R16 and F22: a check that never passes ends the step at `max_iterations`, whatever `retries`
    says. `retries` is for a tool or runner that broke, not for a loop that reached its cap."""
    monkeypatch.setenv("ASAC_RETRIES", "2")
    runner = HostRunner(_wt("cap1"), _agent(fix_from_launch=99))
    r = _drive(project, runner, "apply", "-p", "feature", "--harness", "claude-code",
               "--run-id", "cap1")  # fmt: skip
    log = _log(project, "cap1")
    assert runner.launches == 4, (runner.launches, log)  # max_iterations is 4: no fifth launch
    assert r.exit_code == 1 and "loop cap reached after 4 turns" in log
    assert "step.retry" not in log  # the cap is final: nothing is retried
    assert "5 of 4" not in log and "of 4 failed" in log


def test_a_tool_that_breaks_is_still_retried(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The retry keeps its job: a runner command that exits non-zero is tried again."""
    monkeypatch.setenv("ASAC_RETRIES", "1")
    runner = HostRunner(_wt("cap2"), "exit 3\n")
    r = _drive(project, runner, "apply", "-p", "feature", "--harness", "claude-code",
               "--run-id", "cap2")  # fmt: skip
    log = _log(project, "cap2")
    assert runner.launches == 2 and "step.retry" in log, (runner.launches, log)
    assert r.exit_code == 1
