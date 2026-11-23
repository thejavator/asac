"""ASAC with the real `claude`, on a project that is not the shipped example.

These tests spend money (about 0.30 USD a call) and need the network, so they never run by
accident. They run only when asked: ASAC_REAL_CLAUDE=1 and the tool, node and srt installed.

    ASAC_REAL_CLAUDE=1 uv run pytest tests/test_real_claude.py -m integration -v

What they check is what no stand-in tool can: that the command line ASAC builds is accepted by
the real tool, that its JSON report is read, that its work lands in the worktree and nowhere
else, and that the checks judge that work. They assert on the disk and the audit, never on what
the agent says about itself.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from asac.cli import app
from asac.engine.runtime import store_for
from tests.conftest import init_git

runner = CliRunner()

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("ASAC_REAL_CLAUDE") != "1",
        reason="spends money: set ASAC_REAL_CLAUDE=1 to run it",
    ),
    pytest.mark.skipif(shutil.which("claude") is None, reason="claude is not installed"),
]

# A project that is not the shipped example: another capability, another skill, another hook,
# and a request the agent has never seen. The hook is the check: it passes only if the agent's
# work exists in the worktree and has the shape the step asked for.
MANIFEST = """\
asac: { spec: "0.4", workspace: itest, team: t }
variables:
  tool: { type: harness }
providers:
  llm: { source: asac/claude, version: "~> 1.0", config: {} }
capabilities:
  greeting: { description: Write a greeting file, evidence: [greeting_written] }
evidenceTypes:
  greeting_written: { description: The greeting file exists and says what was asked }
skills:
  greet: { ref: .asac/skills/greet.md, fulfils: greeting }
agents:
  writer: { skill: greet, provider: llm, harness: var.tool }
hooks:
  definitions:
    greeting-ok: { run: .asac/hooks/greeting-ok.sh, on_fail: block }
pipelines:
  hello:
    steps:
      write:
        capability: greeting
        agent: writer
        mode: assist
        producesEvidence: [greeting_written]
        hooks: { post_step: [greeting-ok] }
        gate: { type: human, role: reviewer, timeout: 24h }
"""
SKILL = """\
Write the file `GREETING.txt` at the top of the project. It must contain exactly one line:
`Bonjour, <name>!` where <name> is the name given in `REQUEST.txt`. Write nothing else, and do
not change any other file.
"""
HOOK = """\
#!/bin/sh
# Passes only if GREETING.txt exists and greets the name in REQUEST.txt.
name=$(sed -n 's/^name: *//p' REQUEST.txt)
[ -s GREETING.txt ] || { echo "GREETING.txt is missing or empty" >&2; exit 1; }
want="Bonjour, ${name}!"
got=$(head -n 1 GREETING.txt)
[ "$got" = "$want" ] || { echo "expected '$want', found '$got'" >&2; exit 1; }
"""


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "proj"
    (root / ".asac" / "skills").mkdir(parents=True)
    (root / ".asac" / "hooks").mkdir(parents=True)
    (root / "asac.yaml").write_text(MANIFEST)
    (root / "asac.vars.yaml").write_text("tool: claude-code\nautorun: true\n")
    (root / ".asac" / "skills" / "greet.md").write_text(SKILL)
    (root / ".asac" / "hooks" / "greeting-ok.sh").write_text(HOOK)
    (root / "REQUEST.txt").write_text("name: Zoé\n")
    init_git(root)
    # The real tool needs the user's real HOME (its login); only ASAC's own state is isolated.
    monkeypatch.setenv("ASAC_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("ASAC_AUTORUN", "1")
    monkeypatch.setenv("ASAC_AUTORUN_TIMEOUT", "240")
    monkeypatch.setenv("ASAC_SANDBOX", "0")
    return root


def asac(root: Path, *args: str):  # type: ignore[no-untyped-def]
    return runner.invoke(app, [*args, "-f", str(root / "asac.yaml")])


def _git(cwd: Path, *a: str) -> str:
    return subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True).stdout.strip()


def _audit(root: Path, run_id: str) -> list[tuple[str, str]]:
    return [(a.action, a.detail) for a in store_for(root / "asac.yaml").audit(run_id)]


def test_the_real_tool_does_the_step_in_its_worktree_and_the_checks_judge_it(
    project: Path, tmp_path: Path
) -> None:
    r = asac(project, "apply", "-p", "hello", "--run-id", "real1")
    assert r.exit_code == 2, r.output  # stopped at the gate, not failed or blocked
    work = tmp_path / "state" / "worktrees" / "real1"

    # 1. the work is in the run's worktree, and the main checkout is untouched
    greeting = (work / "GREETING.txt").read_text().strip()
    assert greeting == "Bonjour, Zoé!", greeting
    assert not (project / "GREETING.txt").exists()
    assert _git(project, "status", "--porcelain", "--", ":!.asac-state") == ""

    # 2. the checks ran on that work and passed; the rules were not touched
    actions = dict.fromkeys(a for a, _ in _audit(project, "real1"))
    assert "hook.passed" in actions and "hook.failed" not in actions
    assert "integrity.verified" in actions and "integrity.violated" not in actions

    # 3. the cost is the tool's own report, not a guess
    spend = [d for a, d in _audit(project, "real1") if a == "spend.recorded"][0]
    assert "cost=unknown" not in spend
    cost = float(spend.split("cost_usd=")[1].split()[0])
    assert 0.0 < cost < 5.0, spend

    # 4. the gate is bound to the commit ASAC made, and that commit holds the agent's file
    gate = store_for(project / "asac.yaml").get_gate("gate_real1_write")
    assert gate.subject and _git(work, "rev-parse", "HEAD") == gate.subject
    assert "GREETING.txt" in _git(work, "show", "--name-only", "--format=", gate.subject)
    assert _git(work, "log", "-1", "--format=%an", gate.subject) == "ASAC"

    # 5. the evidence exists only once a person approves it
    assert store_for(project / "asac.yaml").list_evidence("real1") == []
    asac(project, "approve", "gate_real1_write", "--role", "reviewer", "--by", "po")
    ev = {e.evidence_id: e for e in store_for(project / "asac.yaml").list_evidence("real1")}
    assert ev["greeting_written"].bootstrapped is False
    assert "completed" in asac(project, "status").output
    assert asac(project, "evidence", "verify", "real1").exit_code == 0


def test_the_checks_refuse_what_the_real_tool_did_not_do(project: Path, tmp_path: Path) -> None:
    """The same project, a request the work cannot satisfy: the check must say no, for real."""
    skill = project / ".asac" / "skills" / "greet.md"
    skill.write_text("Do not create any file. Reply with the single word: done.\n")
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qam", "lazy"],
                   cwd=project, check=True, capture_output=True)  # fmt: skip
    r = asac(project, "apply", "-p", "hello", "--run-id", "real2")
    assert r.exit_code == 3, r.output  # blocked by the hook: nothing reached a human
    log = _audit(project, "real2")
    assert any(a == "hook.failed" and "GREETING.txt is missing" in d for a, d in log), log
    assert not any(a == "gate.opened" for a, _ in log)
    assert store_for(project / "asac.yaml").list_evidence("real2") == []


# -- the real tool under the real sandbox -------------------------------------------------------

needs_sandbox = pytest.mark.skipif(
    shutil.which("srt") is None or shutil.which("node") is None,
    reason="srt and node >= 22.12 are needed for the sandbox",
)


@needs_sandbox
def test_the_real_tool_still_works_inside_the_sandbox(
    project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """What this proves: the real tool can do its job under the sandbox. The model API is reachable
    through the listed host, its own scratch folder is writable, and the work lands in the
    worktree. It does NOT prove the sandbox blocks anything: asked to overwrite a file outside the
    worktree, the real agent declines on its own (checked: the file stays untouched with the
    sandbox off too). That the sandbox blocks is proved by tests/test_adversarial.py, with tools
    that really try. Needs ASAC_REAL_CLAUDE_HOST (the host of your model API), never guessed."""
    host = os.environ.get("ASAC_REAL_CLAUDE_HOST")
    if not host:
        pytest.skip("set ASAC_REAL_CLAUDE_HOST to the host of your model API")
    monkeypatch.setenv("ASAC_SANDBOX", "1")
    monkeypatch.setenv("ASAC_SANDBOX_DOMAINS", host)
    r = asac(project, "apply", "-p", "hello", "--run-id", "real3")
    assert r.exit_code == 2, r.output
    work = tmp_path / "state" / "worktrees" / "real3"
    assert (work / "GREETING.txt").read_text().strip() == "Bonjour, Zoé!"
    log = _audit(project, "real3")
    assert any(a == "tool.launched" and d.startswith("srt") for a, d in log), log
    assert not any(a == "integrity.violated" for a, _ in log)
