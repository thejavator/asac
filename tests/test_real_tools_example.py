"""examples/real-tools: every supported tool mounts its files and the real hooks run."""

import os
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from asac.cli import app
from tests.conftest import init_git

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "real-tools"
MOUNTED = {
    "claude-code": ".claude/skills/spec/SKILL.md",
    "codex": "AGENTS.md",
    "cursor": ".cursor/rules/asac-spec.mdc",
    "bob": ".bob/skills/spec/SKILL.md",
    "antigravity": ".agent/skills/spec/SKILL.md",
}
runner = CliRunner()


def asac(p: Path, *args: str):  # type: ignore[no-untyped-def]
    return runner.invoke(app, [*args, "-f", str(p / "asac.yaml")])


def _work(project: Path, run_id: str) -> Path:
    """The run's worktree: where a person (or the tool) does the work of a step."""
    return Path(os.environ["ASAC_STATE_DIR"]) / "worktrees" / run_id


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    dest = tmp_path / "real-tools"
    # The example is copied without any asac.vars.yaml (it is git-ignored, a user's own file): the
    # tests that need values copy one from vars/, like a person following the runbook.
    shutil.copytree(EXAMPLE, dest, ignore=shutil.ignore_patterns("asac.vars.yaml", ".DS_Store"))
    shutil.copy(dest / "vars" / "claude-code.yaml", dest / "asac.vars.yaml")
    init_git(dest)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("ASAC_AUTORUN", "0")  # never launch a real tool from the tests
    monkeypatch.setenv("ASAC_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("ASAC_FIXED_TIME", "2026-01-01T00:00:00Z")
    return dest


@pytest.mark.parametrize("tool", sorted(MOUNTED))
def test_tool_mounts_and_hands_off(project: Path, tool: str) -> None:
    shutil.copy(project / "vars" / f"{tool}.yaml", project / "asac.vars.yaml")
    assert asac(project, "validate").exit_code == 0
    r = asac(project, "apply", "-p", "feature", "--run-id", "t1")
    assert r.exit_code == 2 and "handed to a person" in r.stdout
    # the tool works in the run's worktree: the files are there, the main checkout is untouched
    work = Path(os.environ["ASAC_STATE_DIR"]) / "worktrees" / "t1"
    mounted = work / MOUNTED[tool]
    assert mounted.is_file() and "Keep changes small" in mounted.read_text()
    assert not (project / MOUNTED[tool]).exists()


def test_full_flow_runs_real_tests_in_hook(project: Path) -> None:
    assert asac(project, "apply", "-p", "feature", "--run-id", "t1").exit_code == 2
    # recording evidence and approving continue the run by themselves
    (_work(project, "t1") / "SPEC.md").write_text("# Spec\n## Acceptance criteria\n- ok\n")
    r = asac(project, "evidence", "bootstrap", "t1", "--evidence", "spec_reviewed", "--by", "me")
    assert "gate_t1_requirements is pending" in r.output
    r = asac(project, "approve", "gate_t1_requirements", "--role", "product_owner", "--by", "me")
    assert "development handed to a person" in r.output
    # break the code: the post_step hook runs the project's real tests and blocks
    (_work(project, "t1") / "app/todo/__init__.py").write_text("def add(t, x):\n    return 1\n")
    r = asac(project, "evidence", "bootstrap", "t1", "--evidence", "tests_green", "--by", "me")
    assert "tests-green" in r.output and "blocked" in r.output


def test_no_resume_only_records_the_decision(project: Path) -> None:
    asac(project, "apply", "-p", "feature", "--run-id", "t1")
    (_work(project, "t1") / "SPEC.md").write_text("# Spec\n## Acceptance criteria\n- ok\n")
    r = asac(project, "evidence", "bootstrap", "t1", "--evidence", "spec_reviewed", "--no-resume")
    assert "pending" not in r.output
    r = asac(project, "apply", "--resume", "t1")
    assert "gate_t1_requirements is pending" in r.output


def _fake_cli(tmp_path: Path, name: str, code: int = 0) -> Path:
    bindir = tmp_path / "bin"
    bindir.mkdir(exist_ok=True)
    exe = bindir / name
    spec = r'printf "# Spec\n## Acceptance criteria\n- ok\n" > SPEC.md'
    exe.write_text(f'#!/bin/sh\necho "$@" > "$PWD/launched-{name}.txt"\n{spec}\nexit {code}\n')
    exe.chmod(0o755)
    return bindir


@pytest.mark.parametrize("tool,cli", [("claude-code", "claude"), ("codex", "codex")])
def test_autorun_launches_the_tool_but_keeps_the_human_step(
    project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, tool: str, cli: str
) -> None:
    shutil.copy(project / "vars" / f"{tool}.yaml", project / "asac.vars.yaml")
    monkeypatch.setenv("PATH", f"{_fake_cli(tmp_path, cli)}:/usr/bin:/bin")
    monkeypatch.setenv("ASAC_AUTORUN", "1")
    r = asac(project, "apply", "-p", "feature", "--run-id", "t1")
    assert r.exit_code == 2 and "gate_t1_requirements is pending" in r.stdout
    work = Path(os.environ["ASAC_STATE_DIR"]) / "worktrees" / "t1"
    assert "step 'requirements'" in (work / f"launched-{cli}.txt").read_text()
    assert not (project / f"launched-{cli}.txt").exists()


def test_autorun_failure_is_reported(
    project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PATH", f"{_fake_cli(tmp_path, 'claude', 3)}:/usr/bin:/bin")
    monkeypatch.setenv("ASAC_AUTORUN", "1")
    r = asac(project, "apply", "-p", "feature", "--run-id", "t1")
    assert r.exit_code == 1 and "exited with 3" in r.output


def _scripted_cli(tmp_path: Path, body: str) -> Path:
    bindir = tmp_path / "bin"
    bindir.mkdir(exist_ok=True)
    exe = bindir / "claude"
    exe.write_text(f"#!/bin/sh\n{body}\n")
    exe.chmod(0o755)
    return bindir


def test_autorun_good_result_goes_to_the_gate_without_manual_evidence(
    project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bindir = _scripted_cli(tmp_path, 'printf "# Spec\\n## Acceptance criteria\\n- ok\\n" > SPEC.md')
    monkeypatch.setenv("PATH", f"{bindir}:/usr/bin:/bin")
    monkeypatch.setenv("ASAC_AUTORUN", "1")
    r = asac(project, "apply", "-p", "feature", "--run-id", "t1")
    assert r.exit_code == 2 and "gate_t1_requirements" in r.output
    audit = asac(project, "audit", "--format", "csv").stdout
    assert "tool.launched" in audit and "sha256=" in audit and "hook.passed" in audit
    # no manual evidence step: the gate is already open; approving records the evidence
    asac(project, "approve", "gate_t1_requirements", "--role", "product_owner", "--by", "po")
    assert "spec_reviewed" in asac(project, "evidence", "show", "t1").stdout


@pytest.mark.parametrize(
    "body,message",
    [
        ("true", "SPEC.md is missing"),
        ('echo "# Spec" > SPEC.md', "no acceptance criteria"),
        (
            'printf "## Acceptance\\n" > SPEC.md; echo "x = 1" >> app/todo/__init__.py',
            "app/ was modified",
        ),
    ],
)
def test_autorun_bad_result_is_blocked_by_the_hook(
    project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, body: str, message: str
) -> None:
    monkeypatch.setenv("PATH", f"{_scripted_cli(tmp_path, body)}:/usr/bin:/bin")
    monkeypatch.setenv("ASAC_AUTORUN", "1")
    r = asac(project, "apply", "-p", "feature", "--run-id", "t1")
    assert r.exit_code == 3 and message in r.output
    assert (
        not (project / ".asac-state").exists()
        or "spec_reviewed" not in asac(project, "evidence", "show", "t1").stdout
    )


def test_autorun_declared_in_vars_applies_to_every_process(
    project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The setting lives in asac.vars.yaml, so a portal or daemon behaves like the CLI."""
    monkeypatch.delenv("ASAC_AUTORUN")
    shutil.copy(project / "vars" / "codex.yaml", project / "asac.vars.yaml")
    monkeypatch.setenv("PATH", f"{_fake_cli(tmp_path, 'codex')}:/usr/bin:/bin")
    r = asac(project, "apply", "-p", "feature", "--run-id", "t1")
    assert "gate_t1_requirements is pending" in r.stdout


def test_env_overrides_vars_autorun(
    project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    shutil.copy(project / "vars" / "codex.yaml", project / "asac.vars.yaml")
    monkeypatch.setenv("ASAC_AUTORUN", "0")
    monkeypatch.setenv("PATH", f"{_fake_cli(tmp_path, 'codex')}:/usr/bin:/bin")
    r = asac(project, "apply", "-p", "feature", "--run-id", "t1")
    assert "handed to a person" in r.stdout
