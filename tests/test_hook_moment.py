"""The audit says when each hook ran: before the agent (pre_tool) or after the step (post_step)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from asac.cli import app
from asac.engine.runtime import store_for
from tests.conftest import init_git

runner = CliRunner()
EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "real-tools"


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "rt"
    shutil.copytree(EXAMPLE, root, ignore=shutil.ignore_patterns(".DS_Store", ".asac-state"))
    shutil.copy(root / "vars" / "claude-code.yaml", root / "asac.vars.yaml")
    init_git(root)
    bindir = tmp_path / "bin"
    bindir.mkdir()
    (bindir / "claude").write_text(
        "#!/bin/sh\n"
        'printf "# Spec\\n## Acceptance criteria\\n- ok\\n" > SPEC.md\n'
        'echo \'{"type":"result","is_error":false,"total_cost_usd":0.01,'
        '"usage":{},"result":"x"}\'\n'
    )
    (bindir / "claude").chmod(0o755)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("ASAC_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("ASAC_FIXED_TIME", "2026-01-01T00:00:00Z")
    monkeypatch.setenv("ASAC_AUTORUN", "1")
    monkeypatch.setenv("ASAC_SANDBOX", "0")
    monkeypatch.setenv("PATH", f"{bindir}:/usr/bin:/bin")
    return root


def _hooks(project: Path, run_id: str) -> list[tuple[str, str]]:
    """(moment, name) for each hook result, in order, read from the audit's detail."""
    out = []
    for a in store_for(project / "asac.yaml").audit(run_id):
        if a.action in ("hook.passed", "hook.failed"):
            first = a.detail.split("\n", 1)[0]
            moment, _, name = first.partition(" ")
            out.append((moment, name))
    return out


def test_each_hook_result_says_when_it_ran(project: Path) -> None:
    runner.invoke(
        app, ["apply", "-p", "feature", "--run-id", "m1", "-f", str(project / "asac.yaml")]
    )
    # requirements runs the global hook, then its own; tests-green belongs to development only
    assert _hooks(project, "m1") == [
        ("pre_tool", "no-secrets"),
        ("pre_tool", "step-scope"),
        ("post_step", "step-scope"),
    ]


def test_a_loop_check_is_recorded_as_a_loop_check(project: Path) -> None:
    manifest = project / "asac.yaml"
    text = manifest.read_text().replace(
        "        mode: assist\n",
        "        mode: assist\n        loop: { until: [step-scope], max_iterations: 2 }\n",
        1,
    )
    manifest.write_text(text)
    init_git(project) if not (project / ".git").exists() else None
    import subprocess

    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qam", "loop"],
                   cwd=project, check=True, capture_output=True)  # fmt: skip
    runner.invoke(app, ["apply", "-p", "feature", "--run-id", "m2", "-f", str(manifest)])
    detail = [a.detail for a in store_for(manifest).audit("m2") if a.action == "step.iteration"]
    assert detail, "the loop did not run"
