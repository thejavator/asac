"""Regression tests for the review: references, durations, timeouts, instructions."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from asac.cli import app

runner = CliRunner()


def asac(project: Path, *args: str):  # type: ignore[no-untyped-def]
    return runner.invoke(app, [*args, "-f", str(project / "asac.yaml")])


def edit(project: Path, old: str, new: str) -> None:
    f = project / "asac.yaml"
    text = f.read_text()
    assert old in text
    f.write_text(text.replace(old, new, 1))


def test_agent_reference_to_unknown_knowledge_is_an_error(sandbox_project: Path) -> None:
    edit(
        sandbox_project,
        "    tools: [gitlab]\n  qa-agent",
        "    tools: [gitlab]\n    knowledge: [nope]\n  qa-agent",
    )
    r = asac(sandbox_project, "validate")
    assert r.exit_code == 1 and "ASAC022" in r.output


def test_agent_reference_to_unknown_instruction_is_an_error(sandbox_project: Path) -> None:
    edit(
        sandbox_project,
        "    tools: [gitlab]\n  qa-agent",
        "    tools: [gitlab]\n    instructions: [x.md]\n  qa-agent",
    )
    r = asac(sandbox_project, "validate")
    assert r.exit_code == 1 and "ASAC021" in r.output


def test_invalid_duration_is_an_error(sandbox_project: Path) -> None:
    edit(sandbox_project, "wall_clock: 2h", "wall_clock: soon")
    r = asac(sandbox_project, "validate")
    assert r.exit_code == 1 and "ASAC023" in r.output


def test_pipeline_timeout_blocks_a_late_run(
    sandbox_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ASAC_FIXED_TIME", "2026-01-01T00:00:00Z")
    args = ("apply", "-p", "feature", "--harness", "fake", "--run-id", "late")
    assert asac(sandbox_project, *args).exit_code == 2
    assert (
        asac(
            sandbox_project, "approve", "gate_late_requirements", "--role", "product_owner"
        ).exit_code
        == 0
    )
    monkeypatch.setenv("ASAC_FIXED_TIME", "2026-02-01T00:00:00Z")  # a month later, timeout is 72h
    r = asac(sandbox_project, "apply", "--resume", "late", "--harness", "fake")
    assert r.exit_code == 3
    assert "timeout" in r.stdout or "wall-clock" in r.stdout


def test_run_single_step_only(sandbox_project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASAC_FIXED_TIME", "2026-01-01T00:00:00Z")
    r = asac(sandbox_project, "run", "requirements", "-p", "feature", "--harness", "fake")
    assert r.exit_code in (0, 2)
    assert "development" not in r.stdout
