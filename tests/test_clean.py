"""``asac clean``: remove a run's worktree, keep its branch (the work to review)."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from asac.cli import app
from tests.conftest import init_git

runner = CliRunner()


def asac(project: Path, *args: str):  # type: ignore[no-untyped-def]
    return runner.invoke(app, [*args, "-f", str(project / "asac.yaml")])


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=True
    ).stdout.strip()


@pytest.fixture
def project(sandbox_project: Path) -> Path:
    init_git(sandbox_project)
    return sandbox_project


def _work(run_id: str) -> Path:
    return Path(os.environ["ASAC_STATE_DIR"]) / "worktrees" / run_id


def test_clean_removes_the_worktree_and_keeps_the_branch(project: Path) -> None:
    asac(project, "apply", "-p", "feature", "--harness", "claude-code", "--run-id", "k1")
    r = asac(project, "clean", "k1", "--force")  # the run is still waiting: force is explicit
    assert r.exit_code == 0, r.output
    assert not _work("k1").exists()
    assert "asac/k1" in _git(project, "branch", "--list", "asac/k1")


def test_clean_refuses_a_run_that_is_still_waiting(project: Path) -> None:
    """A run waiting for a decision still needs its worktree: it must not be removed."""
    asac(project, "apply", "-p", "feature", "--harness", "claude-code", "--run-id", "k2")
    r = asac(project, "clean", "k2")
    assert r.exit_code == 1 and "still" in r.output.lower()
    assert _work("k2").is_dir()


def test_clean_is_a_noop_for_a_run_without_a_worktree(project: Path) -> None:
    asac(project, "apply", "-p", "feature", "--harness", "fake", "--run-id", "k3")
    r = asac(project, "clean", "k3")
    assert r.exit_code == 0 and "no worktree" in r.output.lower()


def test_clean_twice_is_harmless(project: Path) -> None:
    asac(project, "apply", "-p", "feature", "--harness", "claude-code", "--run-id", "k4")
    asac(project, "evidence", "bootstrap", "k4", "--evidence", "spec_reviewed", "--no-resume")
    (_work("k4") / "SPEC.md").write_text("# Spec\n## Acceptance criteria\n- ok\n")
    first = asac(project, "clean", "k4", "--force")
    second = asac(project, "clean", "k4", "--force")
    assert first.exit_code == 0 and second.exit_code == 0
