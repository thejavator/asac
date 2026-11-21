"""Each step ends in a commit made by ASAC on the run's branch; the gate is bound to that sha."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from asac.cli import app
from tests.conftest import init_git

runner = CliRunner()


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", *args],
        cwd=cwd, capture_output=True, text=True, check=True,
    ).stdout.strip()  # fmt: skip


def asac(project: Path, *args: str):  # type: ignore[no-untyped-def]
    return runner.invoke(app, [*args, "-f", str(project / "asac.yaml")])


@pytest.fixture
def project(sandbox_project: Path) -> Path:
    init_git(sandbox_project)
    return sandbox_project


def _work(run_id: str) -> Path:
    return Path(os.environ["ASAC_STATE_DIR"]) / "worktrees" / run_id


def test_a_finished_step_is_committed_on_the_run_branch(project: Path) -> None:
    asac(project, "apply", "-p", "feature", "--harness", "claude-code", "--run-id", "c1")
    (_work("c1") / "SPEC.md").write_text("# Spec\n## Acceptance criteria\n- ok\n")
    asac(project, "evidence", "bootstrap", "c1", "--evidence", "spec_reviewed", "--no-resume")
    asac(project, "apply", "--resume", "c1")  # the commit happens when the step's hooks pass
    msg = _git(_work("c1"), "log", "-1", "--format=%s")
    assert "requirements" in msg and "c1" in msg
    assert _git(_work("c1"), "status", "--porcelain") == ""


def test_the_evidence_records_the_sha_it_was_produced_on(project: Path) -> None:
    asac(project, "apply", "-p", "feature", "--harness", "claude-code", "--run-id", "c2")
    (_work("c2") / "SPEC.md").write_text("# Spec\n## Acceptance criteria\n- ok\n")
    asac(project, "evidence", "bootstrap", "c2", "--evidence", "spec_reviewed", "--no-resume")
    asac(project, "approve", "gate_c2_requirements", "--role", "product_owner", "--by", "po")
    sha = _git(_work("c2"), "rev-parse", "HEAD")
    assert sha in asac(project, "audit").output or sha in asac(project, "logs", "c2").output


def test_the_gate_names_the_commit_it_approves(project: Path) -> None:
    asac(project, "apply", "-p", "feature", "--harness", "claude-code", "--run-id", "c3")
    (_work("c3") / "SPEC.md").write_text("# Spec\n## Acceptance criteria\n- ok\n")
    asac(project, "evidence", "bootstrap", "c3", "--evidence", "spec_reviewed", "--no-resume")
    sha = _git(_work("c3"), "rev-parse", "HEAD")
    asac(project, "apply", "--resume", "c3")  # the gate opens on resume
    assert "gate_c3_requirements" in asac(project, "gates").output
    assert sha[:12] in asac(project, "logs", "c3").output


def test_the_gate_approves_the_commit_asac_made_not_one_the_agent_made(project: Path) -> None:
    """The agent commits something else on the branch: the gate is bound to ASAC's commit."""
    asac(project, "apply", "-p", "feature", "--harness", "claude-code", "--run-id", "c4")
    (_work("c4") / "SPEC.md").write_text("# Spec\n## Acceptance criteria\n- ok\n")
    _git(_work("c4"), "add", "-A")
    _git(_work("c4"), "commit", "-q", "-m", "agent: something else")
    agent_sha = _git(_work("c4"), "rev-parse", "HEAD")
    asac(project, "evidence", "bootstrap", "c4", "--evidence", "spec_reviewed", "--no-resume")
    asac(project, "apply", "--resume", "c4")
    asac_sha = _git(_work("c4"), "rev-parse", "HEAD")
    assert asac_sha != agent_sha
    assert _git(_work("c4"), "log", "-1", "--format=%an") == "ASAC"
    assert asac_sha[:12] in asac(project, "logs", "c4").output
    assert "step.committed" in asac(project, "logs", "c4").output


def test_the_gate_record_carries_the_commit_it_approves(project: Path) -> None:
    """The approval is about one commit: the gate stores it, so it can be shown and checked."""
    asac(project, "apply", "-p", "feature", "--harness", "claude-code", "--run-id", "c5")
    (_work("c5") / "SPEC.md").write_text("# Spec\n## Acceptance criteria\n- ok\n")
    asac(project, "evidence", "bootstrap", "c5", "--evidence", "spec_reviewed", "--no-resume")
    asac(project, "apply", "--resume", "c5")
    sha = _git(_work("c5"), "rev-parse", "HEAD")
    store = _store(project)
    gate = store.get_gate("gate_c5_requirements")
    assert gate.subject == sha


def test_an_old_database_without_the_column_still_opens(tmp_path: Path) -> None:
    """Migration: a state file created before the subject column keeps working."""
    import sqlite3

    from asac.adapters.state_sqlite import SqliteStateStore

    db = tmp_path / "old.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        """CREATE TABLE runs (run_id TEXT PRIMARY KEY, pipeline TEXT NOT NULL,
             status TEXT NOT NULL, created_at TEXT NOT NULL);
           CREATE TABLE gates (gate_id TEXT PRIMARY KEY, run_id TEXT NOT NULL,
             step_id TEXT NOT NULL, type TEXT NOT NULL, role TEXT, status TEXT NOT NULL,
             requested_at TEXT NOT NULL, timeout_at TEXT, decided_by TEXT, decided_at TEXT,
             comment TEXT, evidence_ids TEXT NOT NULL DEFAULT '[]');"""
    )
    conn.commit()
    conn.close()
    store = SqliteStateStore(db)  # must migrate, not crash
    cols = {r[1] for r in sqlite3.connect(db).execute("PRAGMA table_info(gates)")}
    assert "subject" in cols  # the column really was added to the old table
    store.close()


def _store(project: Path):  # type: ignore[no-untyped-def]
    from asac.engine.runtime import store_for

    return store_for(project / "asac.yaml")


def test_gates_lists_the_commit_each_gate_approves(project: Path) -> None:
    asac(project, "apply", "-p", "feature", "--harness", "claude-code", "--run-id", "c6")
    (_work("c6") / "SPEC.md").write_text("# Spec\n## Acceptance criteria\n- ok\n")
    asac(project, "evidence", "bootstrap", "c6", "--evidence", "spec_reviewed", "--no-resume")
    asac(project, "apply", "--resume", "c6")
    sha = _git(_work("c6"), "rev-parse", "HEAD")
    line = [ln for ln in asac(project, "gates").output.splitlines() if "gate_c6_requirements" in ln]
    assert line and f"commit={sha[:12]}" in line[0]
