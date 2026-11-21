"""``step.loop``: retry an agent with the reason its work was rejected, up to a hard cap."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
from pydantic import ValidationError

from asac.model.manifest import Loop, Step

MINI = """\
asac: { spec: "0.4", workspace: loop, team: t }
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
        mode: assist
        producesEvidence: [built]
        loop: { until: [probe], max_iterations: 3 }
"""


def test_loop_is_accepted_and_bounded() -> None:
    step = Step(capability="c", agent="a", loop={"until": ["probe"], "max_iterations": 3})
    assert isinstance(step.loop, Loop) and step.loop.max_iterations == 3


def test_loop_without_a_cap_is_refused() -> None:
    """A loop with no ceiling could run forever: the cap is mandatory."""
    with pytest.raises(ValidationError):
        Step(capability="c", agent="a", loop={"until": ["probe"]})


@pytest.mark.parametrize("cap", [0, -1, 51])
def test_loop_cap_must_be_between_1_and_50(cap: int) -> None:
    with pytest.raises(ValidationError):
        Step(capability="c", agent="a", loop={"until": ["probe"], "max_iterations": cap})


def test_loop_needs_at_least_one_check() -> None:
    with pytest.raises(ValidationError):
        Step(capability="c", agent="a", loop={"until": [], "max_iterations": 3})


def test_validate_names_an_unknown_loop_check(tmp_path: Path) -> None:
    from typer.testing import CliRunner

    from asac.cli import app

    root = tmp_path / "p"
    (root / ".asac" / "skills").mkdir(parents=True)
    (root / ".asac" / "skills" / "impl.md").write_text("x")
    (root / ".asac" / "hooks").mkdir(parents=True)
    (root / ".asac" / "hooks" / "probe.sh").write_text("exit 0\n")
    (root / "asac.yaml").write_text(MINI.replace("until: [probe]", "until: [nope]"))
    r = CliRunner().invoke(app, ["validate", "-f", str(root / "asac.yaml")])
    assert r.exit_code != 0 and "nope" in r.output


# -- behaviour -----------------------------------------------------------------
# The scripted "agent" is the person of an assist step: each time ASAC hands the step over,
# the test plays the agent by writing into the worktree. The probe hook reads the worktree.

PROBE = 'test -f "$PWD/done.txt" || { echo "done.txt is missing" >&2; exit 1; }\n'


def _loop_project(tmp_path: Path, max_iterations: int = 3) -> Path:
    root = tmp_path / "loopproj"
    (root / ".asac" / "skills").mkdir(parents=True)
    (root / ".asac" / "hooks").mkdir(parents=True)
    (root / ".asac" / "skills" / "impl.md").write_text("Create done.txt.\n")
    (root / ".asac" / "hooks" / "probe.sh").write_text(PROBE)
    text = MINI.replace("max_iterations: 3", f"max_iterations: {max_iterations}")
    (root / "asac.yaml").write_text(text)
    env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}  # fmt: skip
    for args in (["init", "-q", "-b", "main"], ["add", "-A"], ["commit", "-q", "-m", "base"]):
        subprocess.run(
            ["git", *args], cwd=root, check=True, capture_output=True,
            env={**os.environ, **env},
        )  # fmt: skip
    return root


def _drive(root: Path, run_id: str, *args: str):  # type: ignore[no-untyped-def]
    from typer.testing import CliRunner

    from asac.cli import app

    return CliRunner().invoke(app, [*args, "-f", str(root / "asac.yaml")])


@pytest.fixture
def loop_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("ASAC_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("ASAC_FIXED_TIME", "2026-01-01T00:00:00Z")
    return tmp_path


def test_a_failing_check_sends_the_reason_back_and_the_agent_retries(
    loop_env: Path,
) -> None:
    """The checks run when the agent hands its work back (evidence recorded, run resumed)."""
    root = _loop_project(loop_env)
    _drive(root, "l1", "apply", "-p", "feature", "--harness", "claude-code", "--run-id", "l1")
    work = Path(os.environ["ASAC_STATE_DIR"]) / "worktrees" / "l1"
    # turn 1: the agent hands back without the file; the check fails; the reason goes back
    _drive(root, "l1", "evidence", "bootstrap", "l1", "--evidence", "built", "--no-resume")
    _drive(root, "l1", "apply", "--resume", "l1")
    logged = _drive(root, "l1", "logs", "l1").output
    assert "step.iteration build  1 of 3 failed" in logged
    brief = (Path(os.environ["ASAC_STATE_DIR"]) / "briefs" / "l1" / "build.md").read_text()
    assert "done.txt is missing" in brief
    # turn 2: the agent fixes it and hands back; the check passes; the step completes
    (work / "done.txt").write_text("ok")
    _drive(root, "l1", "evidence", "bootstrap", "l1", "--evidence", "built", "--no-resume")
    _drive(root, "l1", "apply", "--resume", "l1")
    log = _drive(root, "l1", "logs", "l1").output
    assert "step.completed build" in log
    assert log.count("step.iteration build") == 2  # both turns are audited, not just the last one


def test_a_check_that_never_passes_fails_the_step_at_the_cap(loop_env: Path) -> None:
    """The hard cap: after max_iterations failed turns the step fails, and is never validated."""
    root = _loop_project(loop_env, max_iterations=2)
    _drive(root, "cap", "apply", "-p", "feature", "--harness", "claude-code", "--run-id", "cap")
    for _ in range(2):  # the agent hands back twice, never producing done.txt
        _drive(root, "cap", "evidence", "bootstrap", "cap", "--evidence", "built", "--no-resume")
        _drive(root, "cap", "apply", "--resume", "cap")
    log = _drive(root, "cap", "logs", "cap").output
    assert "step.iteration build  2 of 2 failed" in log
    assert "loop cap reached after 2 turns" in log
    assert "step.completed build" not in log
    # the step's evidence was recorded by the person, never produced by the step itself
    ev = _drive(root, "cap", "evidence", "show", "cap").output
    assert "bootstrapped" in ev and "produced_by=build" not in ev
    assert "failed" in _drive(root, "cap", "status").output
