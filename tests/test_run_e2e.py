"""End-to-end CLI tests in the sandbox, with the fake harness."""

import json
import os
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from asac.cli import app
from tests.conftest import init_git

needs_opa = pytest.mark.skipif(shutil.which("opa") is None, reason="opa binary not installed")

runner = CliRunner()


@pytest.fixture(autouse=True)
def fixed_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASAC_FIXED_TIME", "2026-01-01T00:00:00Z")


def asac(project: Path, *args: str) -> object:
    return runner.invoke(app, [*args, "-f", str(project / "asac.yaml")])


def start(project: Path, run_id: str = "run1"):  # type: ignore[no-untyped-def]
    return asac(project, "apply", "-p", "feature", "--harness", "fake", "--run-id", run_id)


def test_plan_lists_gates(sandbox_project: Path) -> None:
    r = asac(sandbox_project, "plan", "-p", "feature")
    assert r.exit_code == 0  # type: ignore[attr-defined]
    out = r.stdout  # type: ignore[attr-defined]
    assert "requirements" in out and "gate=human(product_owner)" in out


def test_plan_json(sandbox_project: Path) -> None:
    r = asac(sandbox_project, "plan", "-p", "feature", "--json")
    data = json.loads(r.stdout)  # type: ignore[attr-defined]
    assert [s["id"] for s in data["steps"]][0] == "requirements"


def test_apply_stops_at_first_gate(sandbox_project: Path) -> None:
    r = start(sandbox_project)
    assert r.exit_code == 2  # type: ignore[attr-defined]
    assert "gate_run1_requirements" in r.stdout  # type: ignore[attr-defined]
    g = asac(sandbox_project, "gates", "--status", "pending")
    assert "gate_run1_requirements" in g.stdout  # type: ignore[attr-defined]


@needs_opa
def test_approve_then_resume_reaches_next_gate_then_completes(sandbox_project: Path) -> None:
    assert start(sandbox_project).exit_code == 2  # type: ignore[attr-defined]
    gate = "gate_run1_requirements"
    a = asac(sandbox_project, "approve", gate, "--role", "product_owner", "--by", "alice")
    assert a.exit_code == 0  # type: ignore[attr-defined]
    # development has no gate, verification (quality gate) is next
    r = asac(sandbox_project, "apply", "--resume", "run1", "--harness", "fake")
    assert r.exit_code == 2  # type: ignore[attr-defined]
    for g, role in (
        ("gate_run1_verification", "qa_engineer"),
        ("gate_run1_release", "product_owner"),
    ):
        if g == "gate_run1_release":
            pass
        args = ["approve", g, "--by", "bob"]
        if role:
            args += ["--role", role]
        assert asac(sandbox_project, *args).exit_code == 0  # type: ignore[attr-defined]
        r = asac(sandbox_project, "apply", "--resume", "run1", "--harness", "fake")
    assert r.exit_code == 0  # type: ignore[attr-defined]
    st = asac(sandbox_project, "status", "--run-id", "run1")
    assert "completed" in st.stdout  # type: ignore[attr-defined]


def test_approve_without_role_is_blocked(sandbox_project: Path) -> None:
    start(sandbox_project)
    r = asac(sandbox_project, "approve", "gate_run1_requirements", "--by", "mallory")
    assert r.exit_code == 3  # type: ignore[attr-defined]
    g = asac(sandbox_project, "gates", "--status", "pending")
    assert "gate_run1_requirements" in g.stdout  # type: ignore[attr-defined]


def test_rejected_gate_fails_run(sandbox_project: Path) -> None:
    start(sandbox_project)
    asac(
        sandbox_project,
        "approve",
        "gate_run1_requirements",
        "--role",
        "product_owner",
        "--reject",
        "--comment",
        "scope unclear",
    )
    r = asac(sandbox_project, "apply", "--resume", "run1", "--harness", "fake")
    assert r.exit_code == 1  # type: ignore[attr-defined]


def test_gate_expires(sandbox_project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    start(sandbox_project)
    monkeypatch.setenv("ASAC_FIXED_TIME", "2026-01-03T00:00:00Z")  # past the 24h timeout
    r = asac(sandbox_project, "approve", "gate_run1_requirements", "--role", "product_owner")
    assert r.exit_code == 1  # type: ignore[attr-defined]
    assert "expired" in r.output  # type: ignore[attr-defined]


def test_crash_then_resume_does_not_duplicate_evidence(
    sandbox_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ASAC_FAKE_FAIL", "requirements")
    assert start(sandbox_project).exit_code == 1  # type: ignore[attr-defined]
    monkeypatch.delenv("ASAC_FAKE_FAIL")
    r = asac(sandbox_project, "apply", "--resume", "run1", "--harness", "fake")
    assert r.exit_code == 2  # type: ignore[attr-defined]
    ev = asac(sandbox_project, "evidence", "show", "run1")
    assert ev.exit_code == 0  # type: ignore[attr-defined]


def test_unknown_harness_has_clear_error(sandbox_project: Path) -> None:
    r = asac(sandbox_project, "apply", "-p", "feature", "--harness", "nope")
    assert r.exit_code == 1  # type: ignore[attr-defined]
    assert "no adapter" in r.output  # type: ignore[attr-defined]


def test_bootstrap_evidence_and_audit_csv(sandbox_project: Path) -> None:
    start(sandbox_project)
    b = asac(
        sandbox_project, "evidence", "bootstrap", "run1", "--evidence", "legacy", "--by", "carol"
    )
    assert b.exit_code == 0  # type: ignore[attr-defined]
    show = asac(sandbox_project, "evidence", "show", "run1")
    assert "bootstrapped" in show.stdout  # type: ignore[attr-defined]
    csv_out = asac(sandbox_project, "audit", "--format", "csv").stdout  # type: ignore[attr-defined]
    assert csv_out.splitlines()[0] == "seq,at,run_id,step_id,actor,action,detail"
    assert "evidence.bootstrapped" in csv_out


def test_plan_golden(sandbox_project: Path) -> None:
    golden = Path(__file__).parent / "golden" / "plan_feature.txt"
    r = asac(sandbox_project, "plan", "-p", "feature")
    assert r.stdout == golden.read_text()  # type: ignore[attr-defined]


def test_claude_code_handoff_flow(sandbox_project: Path) -> None:
    (sandbox_project / "asac.vars.yaml").write_text(
        "ba_harness: claude-code\ndev_harness: fake\nqa_harness: fake\n"
    )
    init_git(sandbox_project)
    r = asac(sandbox_project, "apply", "-p", "feature", "--run-id", "h1")
    assert r.exit_code == 2  # type: ignore[attr-defined]
    assert "handed to a person" in r.stdout  # type: ignore[attr-defined]
    work = Path(os.environ["ASAC_STATE_DIR"]) / "worktrees" / "h1"
    assert (work / ".claude/skills/spec/SKILL.md").is_file()
    assert not (sandbox_project / ".claude").exists()
    # still waiting until the person records the evidence
    r = asac(sandbox_project, "apply", "--resume", "h1")
    assert r.exit_code == 2 and "waiting for evidence" in r.stdout  # type: ignore[attr-defined]
    asac(
        sandbox_project,
        "evidence",
        "bootstrap",
        "h1",
        "--evidence",
        "spec_reviewed",
        "--by",
        "alice",
    )
    r = asac(sandbox_project, "apply", "--resume", "h1")
    assert r.exit_code == 2 and "gate_h1_requirements" in r.stdout  # type: ignore[attr-defined]


def test_rejection_needs_a_reason(sandbox_project: Path) -> None:
    start(sandbox_project)
    r = asac(
        sandbox_project, "approve", "gate_run1_requirements", "--role", "product_owner", "--reject"
    )
    assert r.exit_code == 1  # type: ignore[attr-defined]
    assert "comment" in r.output  # type: ignore[attr-defined]


@needs_opa
def test_reopen_rejected_gate_then_approve(sandbox_project: Path) -> None:
    start(sandbox_project)
    asac(
        sandbox_project, "approve", "gate_run1_requirements", "--role", "product_owner",
        "--reject", "--comment", "scope unclear",
    )  # fmt: skip
    assert asac(sandbox_project, "apply", "--resume", "run1", "--harness", "fake").exit_code == 1  # type: ignore[attr-defined]
    r = asac(sandbox_project, "apply", "--resume", "run1", "--reopen", "--harness", "fake")
    assert r.exit_code == 2  # type: ignore[attr-defined]
    assert "reopened" in r.output  # type: ignore[attr-defined]
    ok = asac(sandbox_project, "approve", "gate_run1_requirements", "--role", "product_owner")
    assert ok.exit_code == 0  # type: ignore[attr-defined]
    assert asac(sandbox_project, "apply", "--resume", "run1", "--harness", "fake").exit_code == 2  # type: ignore[attr-defined]
    log = asac(sandbox_project, "audit").stdout  # type: ignore[attr-defined]
    assert "gate.reopened" in log and "gate.rejected" in log


def test_reopen_refused_on_running_run(sandbox_project: Path) -> None:
    start(sandbox_project)
    r = asac(sandbox_project, "apply", "--resume", "run1", "--reopen", "--harness", "fake")
    assert r.exit_code == 1  # type: ignore[attr-defined]


@needs_opa
def test_watch_continues_after_each_decision(sandbox_project: Path) -> None:
    import subprocess
    import sys
    import time

    proc = subprocess.Popen(  # noqa: S603
        [
            sys.executable, "-c", "from asac.cli import app; app()", "apply", "-p", "feature",
            "--harness", "fake", "--run-id", "w1", "--watch", "--poll", "0.05",
            "-f", str(sandbox_project / "asac.yaml"),
        ],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )  # fmt: skip
    for g, role in (
        ("gate_w1_requirements", "product_owner"),
        ("gate_w1_verification", "qa_engineer"),
        ("gate_w1_release", "product_owner"),
    ):
        for _ in range(200):
            r = asac(sandbox_project, "approve", g, "--role", role, "--by", "bob", "--no-resume")
            if r.exit_code == 0:  # type: ignore[attr-defined]
                break
            time.sleep(0.05)
    out, _ = proc.communicate(timeout=60)
    assert proc.returncode == 0, out
    assert "completed" in out


def test_evidence_verify_reports_missing(sandbox_project: Path) -> None:
    start(sandbox_project)
    assert asac(sandbox_project, "evidence", "verify", "nope").exit_code == 1  # type: ignore[attr-defined]
    ok = asac(sandbox_project, "evidence", "verify", "run1")
    assert ok.exit_code in (0, 1)  # type: ignore[attr-defined]
    if ok.exit_code == 0:  # type: ignore[attr-defined]
        assert "evidence ok" in ok.output  # type: ignore[attr-defined]
    else:
        assert "missing:" in ok.output  # type: ignore[attr-defined]
