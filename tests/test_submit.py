"""`asac submit`: a person hands a step back. The evidence exists only if the checks passed."""

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
EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "real-tools"


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "rt"
    shutil.copytree(EXAMPLE, root, ignore=shutil.ignore_patterns(".DS_Store", "asac.vars.yaml"))
    shutil.copy(root / "vars" / "claude-code.yaml", root / "asac.vars.yaml")
    init_git(root)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.delenv("ASAC_STATE_DIR", raising=False)
    monkeypatch.setenv("ASAC_FIXED_TIME", "2026-01-01T09:00:00Z")
    monkeypatch.setenv("ASAC_AUTORUN", "0")  # the person does the work
    monkeypatch.setenv("ASAC_SANDBOX", "0")
    return root


def asac(root: Path, *args: str):  # type: ignore[no-untyped-def]
    return runner.invoke(app, [*args, "-f", str(root / "asac.yaml")])


def _work(root: Path, run_id: str) -> Path:
    return root / ".asac-state" / "worktrees" / run_id


def _evidence(root: Path, run_id: str) -> dict[str, object]:
    return {e.evidence_id: e for e in store_for(root / "asac.yaml").list_evidence(run_id)}


def _to_development(root: Path, run_id: str) -> None:
    asac(root, "apply", "-p", "feature", "--harness", "claude-code", "--run-id", run_id)
    (_work(root, run_id) / "SPEC.md").write_text("# Spec\n## Acceptance criteria\n- ok\n")
    asac(root, "submit", run_id, "--by", "dev")
    asac(root, "approve", f"gate_{run_id}_requirements", "--role", "product_owner", "--by", "po")


# -- apply tells where the work is -------------------------------------------------------------


def test_apply_shows_the_worktree_and_how_to_enter_it(project: Path) -> None:
    r = asac(project, "apply", "-p", "feature", "--harness", "claude-code", "--run-id", "w1")
    work = _work(project, "w1")
    assert str(work) in r.output, r.output
    assert f"cd {work}" in r.output
    assert "asac submit w1" in r.output


# -- submit records nothing the checks refused ------------------------------------------------


def test_submit_needs_no_evidence_name(project: Path) -> None:
    asac(project, "apply", "-p", "feature", "--harness", "claude-code", "--run-id", "s1")
    (_work(project, "s1") / "SPEC.md").write_text("# Spec\n## Acceptance criteria\n- ok\n")
    r = asac(project, "submit", "s1", "--by", "dev")
    assert r.exit_code in (0, 2), r.output
    assert "gate_s1_requirements" in r.output


def test_a_failed_check_records_no_evidence(project: Path) -> None:
    """The reported defect: tests_green was recorded while the tests failed, and verify said ok."""
    _to_development(project, "s2")
    (_work(project, "s2") / "app" / "todo" / "__init__.py").write_text(
        "def add(t, x):\n    return 1\n"
    )
    r = asac(project, "submit", "s2", "--by", "dev")
    assert r.exit_code == 3, r.output
    assert "tests-green" in r.output
    assert "tests_green" not in _evidence(project, "s2")
    verify = asac(project, "evidence", "verify", "s2")
    assert "tests_green" not in verify.output or verify.exit_code != 0


def test_a_passing_check_records_the_evidence_as_the_persons_work(project: Path) -> None:
    asac(project, "apply", "-p", "feature", "--harness", "claude-code", "--run-id", "s3")
    (_work(project, "s3") / "SPEC.md").write_text("# Spec\n## Acceptance criteria\n- ok\n")
    asac(project, "submit", "s3", "--by", "dev")
    asac(project, "approve", "gate_s3_requirements", "--role", "product_owner", "--by", "po")
    ev = _evidence(project, "s3")["spec_reviewed"]
    assert ev.produced_by == "requirements"  # type: ignore[attr-defined]
    assert ev.bootstrapped is False  # type: ignore[attr-defined]  # done in the run, checked


def test_after_a_failed_check_the_person_fixes_it_and_submits_again(project: Path) -> None:
    _to_development(project, "s4")
    todo = _work(project, "s4") / "app" / "todo" / "__init__.py"
    good = todo.read_text()
    todo.write_text("def add(t, x):\n    return 1\n")
    assert asac(project, "submit", "s4", "--by", "dev").exit_code == 3
    todo.write_text(good)
    r = asac(project, "submit", "s4", "--by", "dev")
    assert "gate_s4_development" in r.output, r.output


def test_submit_is_audited_with_who_handed_the_step_back(project: Path) -> None:
    asac(project, "apply", "-p", "feature", "--harness", "claude-code", "--run-id", "s5")
    (_work(project, "s5") / "SPEC.md").write_text("# Spec\n## Acceptance criteria\n- ok\n")
    asac(project, "submit", "s5", "--by", "dev")
    rows = [(a.actor, a.action) for a in store_for(project / "asac.yaml").audit("s5")]
    assert ("dev", "step.submitted") in rows, rows


def test_submit_refuses_a_step_that_is_not_waiting_for_a_person(project: Path) -> None:
    asac(project, "apply", "-p", "feature", "--harness", "claude-code", "--run-id", "s6")
    (_work(project, "s6") / "SPEC.md").write_text("# Spec\n## Acceptance criteria\n- ok\n")
    asac(project, "submit", "s6", "--by", "dev")  # now at the gate, not with the person
    r = asac(project, "submit", "s6", "--by", "dev")
    assert r.exit_code == 1 and "not waiting" in r.output.lower(), r.output


def test_submit_of_an_unknown_run_is_an_error(project: Path) -> None:
    r = asac(project, "submit", "nope", "--by", "dev")
    assert r.exit_code == 1 and "not found" in r.output


def test_the_handoff_message_points_to_submit(project: Path) -> None:
    asac(project, "apply", "-p", "feature", "--harness", "claude-code", "--run-id", "s7")
    r = asac(project, "apply", "--resume", "s7")
    assert "asac submit s7" in r.output and "evidence bootstrap" not in r.output, r.output


def test_bootstrap_still_records_evidence_made_outside_asac(project: Path) -> None:
    """Kept for its real use: a fact produced elsewhere (an imported security review)."""
    asac(project, "apply", "-p", "feature", "--harness", "claude-code", "--run-id", "s8")
    r = asac(project, "evidence", "bootstrap", "s8", "--evidence", "spec_reviewed", "--by", "sec",
             "--no-resume")  # fmt: skip
    assert r.exit_code == 0
    assert _evidence(project, "s8")["spec_reviewed"].bootstrapped is True  # type: ignore[attr-defined]


def test_the_main_checkout_stays_clean_through_submit(project: Path) -> None:
    _to_development(project, "s9")
    status = subprocess.run(["git", "status", "--porcelain", "--", ":!.asac-state"],
                            cwd=project, capture_output=True, text=True).stdout  # fmt: skip
    assert status == "", status
    assert os.path.isdir(_work(project, "s9"))
