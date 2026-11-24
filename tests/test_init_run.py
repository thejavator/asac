"""`asac init` makes a project that runs; `vars` works before any values file exists."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from asac.cli import app
from tests.conftest import init_git

runner = CliRunner()


@pytest.fixture
def fresh(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    project = tmp_path / "proj"
    project.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.delenv("ASAC_STATE_DIR", raising=False)  # state stays in the project
    monkeypatch.setenv("ASAC_FIXED_TIME", "2026-01-01T09:00:00Z")
    monkeypatch.setenv("ASAC_AUTORUN", "0")
    monkeypatch.setenv("ASAC_SANDBOX", "0")
    return project


def asac(project: Path, *args: str):  # type: ignore[no-untyped-def]
    return runner.invoke(app, [*args, "-f", str(project / "asac.yaml")])


def test_feature_template_writes_a_complete_project(fresh: Path) -> None:
    r = runner.invoke(app, ["init", str(fresh), "--template", "feature"])
    assert r.exit_code == 0, r.output
    for rel in (
        "asac.yaml",
        "asac.vars.yaml.example",
        ".asac/skills/spec.md",
        ".asac/skills/impl.md",
        ".asac/instructions/style.md",
        ".asac/hooks/no-secrets.sh",
        ".asac/hooks/spec-present.sh",
        ".asac/hooks/tests-green.sh",
    ):
        assert (fresh / rel).is_file(), rel
    assert "workspace: proj" in (fresh / "asac.yaml").read_text()
    assert (fresh / ".asac/hooks/tests-green.sh").stat().st_mode & 0o111  # executable


def test_feature_template_validates_without_warning(fresh: Path) -> None:
    runner.invoke(app, ["init", str(fresh), "--template", "feature"])
    r = asac(fresh, "validate")
    assert r.exit_code == 0 and "0 error(s), 0 warning(s)" in r.output, r.output


def test_gitignore_is_created_and_completed_not_overwritten(fresh: Path) -> None:
    (fresh / ".gitignore").write_text("node_modules/\nasac.vars.yaml\n")
    runner.invoke(app, ["init", str(fresh), "--template", "feature"])
    lines = (fresh / ".gitignore").read_text().splitlines()
    assert lines.count("asac.vars.yaml") == 1  # not duplicated
    assert "node_modules/" in lines and ".asac-state/" in lines


def test_init_refuses_to_overwrite_without_force(fresh: Path) -> None:
    runner.invoke(app, ["init", str(fresh), "--template", "feature"])
    (fresh / ".asac/skills/spec.md").write_text("my own spec skill\n")
    assert runner.invoke(app, ["init", str(fresh), "--template", "feature"]).exit_code == 1
    assert (fresh / ".asac/skills/spec.md").read_text() == "my own spec skill\n"
    assert (
        runner.invoke(app, ["init", str(fresh), "--template", "feature", "--force"]).exit_code == 0
    )
    assert "analyst" in (fresh / ".asac/skills/spec.md").read_text()


def test_vars_before_any_values_file(fresh: Path) -> None:
    runner.invoke(app, ["init", str(fresh), "--template", "feature"])
    assert not (fresh / "asac.vars.yaml").exists()
    r = asac(fresh, "vars", "check")
    assert r.exit_code == 1 and "missing: tool" in r.output, r.output
    assert "not found" not in r.output
    (fresh / "asac.vars.yaml").write_text((fresh / "asac.vars.yaml.example").read_text())
    assert asac(fresh, "vars", "check").exit_code == 0
    assert asac(fresh, "vars", "diff").exit_code == 0


def test_the_generated_project_runs_to_its_first_gate(fresh: Path) -> None:
    runner.invoke(app, ["init", str(fresh), "--template", "feature"])
    (fresh / "REQUEST.md").write_text("Add a function double(n).\n")
    (fresh / "asac.vars.yaml").write_text("tool: claude-code\n")
    init_git(fresh)
    # The person does the work in the run's worktree, then hands the step back.
    r = asac(fresh, "apply", "-p", "feature", "--harness", "claude-code", "--run-id", "g1")
    assert r.exit_code == 2, r.output
    work = fresh / ".asac-state" / "worktrees" / "g1"
    r = asac(fresh, "submit", "g1", "--by", "dev")
    assert r.exit_code == 3, r.output  # SPEC.md is missing: the check refuses it
    assert "SPEC.md is missing" in r.output
    (work / "SPEC.md").write_text("# Spec\n## Acceptance criteria\n- double(2) == 4\n")
    r = asac(fresh, "submit", "g1", "--by", "dev")
    assert r.exit_code == 2 and "gate_g1_requirements" in r.output, r.output


def test_run_stops_at_the_first_gate_and_names_it(fresh: Path) -> None:
    runner.invoke(app, ["init", str(fresh), "--template", "feature"])
    (fresh / "asac.vars.yaml").write_text("tool: claude-code\n")
    init_git(fresh)
    r = asac(fresh, "run", "--harness", "claude-code")
    assert r.exit_code == 2, r.output  # the step waits for a person
    assert "work in:" in r.output


def test_run_one_step_still_checks_its_dependencies(fresh: Path) -> None:
    runner.invoke(app, ["init", str(fresh), "--template", "feature"])
    (fresh / "asac.vars.yaml").write_text("tool: claude-code\n")
    init_git(fresh)
    r = asac(fresh, "run", "development", "--harness", "claude-code")
    assert r.exit_code == 3, r.output
    assert "dependencies not completed: requirements" in r.output


def test_learn_writes_a_proposal_and_never_applies_it(fresh: Path) -> None:
    runner.invoke(app, ["init", str(fresh), "--template", "feature"])
    (fresh / "asac.vars.yaml").write_text("tool: claude-code\n")
    init_git(fresh)
    asac(fresh, "run", "development", "--harness", "claude-code")  # blocked: no spec yet
    run_id = asac(fresh, "status").output.split()[0]
    before = (fresh / "asac.yaml").read_text()
    r = asac(fresh, "learn", run_id)
    assert r.exit_code == 0, r.output
    proposal = (fresh / ".asac" / "proposals" / f"{run_id}.md").read_text()
    assert "step.blocked" in proposal and "dependencies not completed" in proposal
    assert (fresh / "asac.yaml").read_text() == before
    assert subprocess.run(["git", "status", "--porcelain", "asac.yaml"], cwd=fresh,
                          capture_output=True, text=True).stdout == ""  # fmt: skip


def test_minimal_template_creates_the_manifest_and_no_other_file(fresh: Path) -> None:
    """F66.8: an empty valid manifest, and nothing else (no template files, no .gitignore)."""
    r = runner.invoke(app, ["init", str(fresh), "--template", "minimal"])
    assert r.exit_code == 0, r.output
    files = sorted(p.relative_to(fresh).as_posix() for p in fresh.rglob("*") if p.is_file())
    assert files == ["asac.yaml"]
    assert asac(fresh, "validate").exit_code == 0


def test_vars_diff_before_any_values_file_lists_the_same_variables(fresh: Path) -> None:
    """F65.2: `vars diff` agrees with `vars check` in a project that has no values file yet."""
    runner.invoke(app, ["init", str(fresh), "--template", "feature"])
    check = asac(fresh, "vars", "check")
    diff = asac(fresh, "vars", "diff")
    assert diff.exit_code == 1 and check.exit_code == 1
    assert "missing: tool" in diff.output and "not found" not in diff.output
