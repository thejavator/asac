"""F57.1 and F69.3: the real `claude`, in the real container, through the real engine.

Spends money (about 0.10 to 0.30 USD) and needs the network, the Docker image and a model API, so
it runs only when asked:

    ASAC_REAL_CLAUDE=1 ASAC_REAL_CLAUDE_NETWORK=<docker network> \\
        uv run pytest tests/test_delegate_real.py -m integration -v

The runner's default network is `none`, which also cuts the model API: for a real agent the
operator names a Docker network that reaches the gateway (`ASAC_REAL_CLAUDE_NETWORK`, default
`bridge`). The key and gateway address are passed to the container by name from the environment
(`ANTHROPIC_*`) and never written anywhere.

What is checked is the disk and the audit, never what the agent says about itself.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from asac.adapters.runner_local import DEFAULT_IMAGE
from asac.cli import app
from asac.engine.runtime import store_for
from tests.conftest import init_git

runner = CliRunner()


def _image_present() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        probe = ["docker", "image", "inspect", DEFAULT_IMAGE]
        return subprocess.run(probe, capture_output=True, timeout=15).returncode == 0
    except subprocess.TimeoutExpired:
        return False


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("ASAC_REAL_CLAUDE") != "1",
        reason="spends money: set ASAC_REAL_CLAUDE=1 to run it",
    ),
    pytest.mark.skipif(not _image_present(), reason=f"the image {DEFAULT_IMAGE} is not built"),
]

MANIFEST = """\
asac: { spec: "0.4", workspace: dreal, team: t }
providers:
  llm: { source: asac/claude, version: "~> 1.0", config: {} }
capabilities:
  greeting: { description: Write a greeting file, evidence: [greeting_written] }
evidenceTypes:
  greeting_written: { description: The greeting file exists and says what was asked }
skills:
  greet: { ref: .asac/skills/greet.md, fulfils: greeting }
agents:
  writer: { skill: greet, provider: llm, harness: claude-code }
hooks:
  definitions:
    greeting-ok: { run: .asac/hooks/greeting-ok.sh, on_fail: block }
pipelines:
  hello:
    steps:
      write:
        capability: greeting
        agent: writer
        mode: delegate
        execution: { runner: docker }
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
name=$(sed -n 's/^name: *//p' REQUEST.txt)
[ -s GREETING.txt ] || { echo "GREETING.txt is missing or empty" >&2; exit 1; }
want="Bonjour, ${name}!"
got=$(head -n 1 GREETING.txt)
[ "$got" = "$want" ] || { echo "expected '$want', found '$got'" >&2; exit 1; }
"""


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    for name in ("ANTHROPIC_BASE_URL", "ANTHROPIC_AUTH_TOKEN"):
        if not os.environ.get(name) and not os.environ.get("ANTHROPIC_API_KEY"):
            pytest.skip(f"{name} (or ANTHROPIC_API_KEY) is not set: the container cannot log in")
    root = tmp_path / "proj"
    (root / ".asac" / "skills").mkdir(parents=True)
    (root / ".asac" / "hooks").mkdir(parents=True)
    (root / "asac.yaml").write_text(MANIFEST)
    names = [n for n in (
        "ANTHROPIC_BASE_URL", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_API_KEY", "ANTHROPIC_MODEL",
        "CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS",
    ) if os.environ.get(n)]  # fmt: skip
    network = os.environ.get("ASAC_REAL_CLAUDE_NETWORK", "bridge")
    (root / "asac.vars.yaml").write_text(
        f"runner_kind: docker\nrunner_network: {network}\nrunner_env: {','.join(names)}\n"
    )
    (root / ".asac" / "skills" / "greet.md").write_text(SKILL)
    (root / ".asac" / "hooks" / "greeting-ok.sh").write_text(HOOK)
    (root / ".asac" / "hooks" / "greeting-ok.sh").chmod(0o755)
    (root / "REQUEST.txt").write_text("name: Zoé\n")
    init_git(root)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("ASAC_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("ASAC_AUTORUN", "0")  # delegation is not autorun
    monkeypatch.setenv("ASAC_SANDBOX", "0")
    return root


def asac(root: Path, *args: str):  # type: ignore[no-untyped-def]
    return runner.invoke(app, [*args, "-f", str(root / "asac.yaml")])


def _audit(root: Path, run_id: str) -> list[tuple[str, str]]:
    return [(a.action, a.detail) for a in store_for(root / "asac.yaml").audit(run_id)]


def test_the_real_claude_does_the_step_in_the_container_and_the_checks_judge_it(
    project: Path, tmp_path: Path
) -> None:
    r = asac(project, "apply", "-p", "hello", "--run-id", "dreal")
    assert r.exit_code == 2, r.output  # stopped at the gate, not failed or blocked
    work = tmp_path / "state" / "worktrees" / "dreal"

    # the agent's work is in the run's worktree on the host, and the main checkout is untouched
    assert (work / "GREETING.txt").read_text().strip() == "Bonjour, Zoé!"
    assert not (project / "GREETING.txt").exists()
    # the tool's own files (login, sessions, history) went to the container's scratch space; the
    # only thing under .claude/ is the skill ASAC mounted
    assert not (work / ".claude.json").exists()
    mounted = sorted(
        p.relative_to(work).as_posix() for p in (work / ".claude").rglob("*") if p.is_file()
    )
    assert mounted == [".claude/skills/greet/SKILL.md"], mounted

    actions = dict.fromkeys(a for a, _ in _audit(project, "dreal"))
    for event in (
        "runner.started", "runner.output", "runner.stopped", "tool.launched",
        "hook.passed", "integrity.verified", "step.committed", "gate.opened",
    ):  # fmt: skip
        assert event in actions, event
    assert "hook.failed" not in actions and "integrity.violated" not in actions

    # the cost is the tool's own report, read from the container's output
    spend = [d for a, d in _audit(project, "dreal") if a == "spend.recorded"][0]
    assert "cost=unknown" not in spend
    assert 0.0 < float(spend.split("cost_usd=")[1].split()[0]) < 5.0, spend

    # no credential reached the audit or the stored output
    secret = os.environ.get("ANTHROPIC_AUTH_TOKEN") or os.environ.get("ANTHROPIC_API_KEY", "")
    if len(secret) >= 8:
        for _, detail in _audit(project, "dreal"):
            assert secret not in detail
        for artefact in (tmp_path / "state" / "artifacts").rglob("*"):
            if artefact.is_file():
                assert secret not in artefact.read_text(errors="ignore")

    # the gate is bound to the commit ASAC made in the worktree, which holds the agent's file
    gate = store_for(project / "asac.yaml").get_gate("gate_dreal_write")
    shown = subprocess.run(["git", "show", "--name-only", "--format=", str(gate.subject)],
                           cwd=work, capture_output=True, text=True).stdout  # fmt: skip
    assert "GREETING.txt" in shown
