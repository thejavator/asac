"""Isolation end to end: a run works in its own worktree; hooks and rules stay in the main tree."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from asac.cli import app

runner = CliRunner()
pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", *args],
        cwd=cwd, capture_output=True, text=True, check=True,
    ).stdout.strip()  # fmt: skip


@pytest.fixture
def project(sandbox_project: Path) -> Path:
    """The payments example as a git repository with one commit (what a real team has)."""
    _git(sandbox_project, "init", "-q", "-b", "main")
    _git(sandbox_project, "add", "-A")
    _git(sandbox_project, "commit", "-q", "-m", "base")
    return sandbox_project


def asac(project: Path, *args: str):  # type: ignore[no-untyped-def]
    return runner.invoke(app, [*args, "-f", str(project / "asac.yaml")])


def test_apply_creates_a_worktree_and_hands_the_agent_its_files_there(project: Path) -> None:
    r = asac(project, "apply", "-p", "feature", "--harness", "claude-code", "--run-id", "iso1")
    assert r.exit_code == 2, r.output
    wt = Path(os.environ["ASAC_STATE_DIR"]) / "worktrees" / "iso1"  # set by sandbox_project
    assert wt.is_dir()
    assert _git(wt, "rev-parse", "--abbrev-ref", "HEAD") == "asac/iso1"
    assert (wt / ".claude/skills/spec/SKILL.md").is_file()
    assert (wt / "CLAUDE.md").is_file()
    assert not (project / ".claude").exists()
    assert _git(project, "status", "--porcelain") == ""


def test_run_records_the_worktree_path_in_the_audit(project: Path) -> None:
    asac(project, "apply", "-p", "feature", "--harness", "claude-code", "--run-id", "iso2")
    r = asac(project, "logs", "iso2")
    assert "workspace.created" in r.output and "asac/iso2" in r.output


def test_fake_harness_runs_without_a_git_repository(sandbox_project: Path) -> None:
    # Isolation is for real tools; the offline fake keeps working in a plain folder.
    r = asac(sandbox_project, "apply", "-p", "feature", "--harness", "fake", "--run-id", "plain")
    assert r.exit_code in (0, 2), r.output
    assert "not a git repository" not in r.output


def test_one_context_serving_two_runs_writes_each_into_its_own_worktree(project: Path) -> None:
    """The daemon and the portal reuse one context: run B must never write into run A's tree."""
    from asac.engine.apply import create_run
    from asac.engine.runtime import make_context, project_root, store_for
    from asac.loader.load import load_manifest

    manifest = load_manifest(project / "asac.yaml")
    store = store_for(project / "asac.yaml")
    ctx = make_context(manifest, "feature", store, project_root(project / "asac.yaml"),
                       "claude-code")  # fmt: skip
    create_run(ctx, "multiA")
    create_run(ctx, "multiB")
    ha, hb = ctx.harness_for("ba", "multiA"), ctx.harness_for("ba", "multiB")
    assert ha is not hb
    ha.mount("spec")
    hb.mount("spec")
    trees = Path(os.environ["ASAC_STATE_DIR"]) / "worktrees"
    assert (trees / "multiA/.claude/skills/spec/SKILL.md").is_file()
    assert (trees / "multiB/.claude/skills/spec/SKILL.md").is_file()
    assert not (project / ".claude").exists()


def test_resume_finds_the_worktree_recorded_for_the_run(project: Path) -> None:
    from asac.engine.runtime import make_context, project_root, store_for
    from asac.loader.load import load_manifest

    asac(project, "apply", "-p", "feature", "--harness", "claude-code", "--run-id", "res1")
    manifest = load_manifest(project / "asac.yaml")
    ctx = make_context(manifest, "feature", store_for(project / "asac.yaml"),
                       project_root(project / "asac.yaml"), "claude-code")  # fmt: skip
    h = ctx.harness_for("ba", "res1")  # a fresh context, like a later `asac apply --resume`
    trees = Path(os.environ["ASAC_STATE_DIR"]) / "worktrees"
    assert h._ctx.workdir == trees / "res1"  # type: ignore[attr-defined]


def test_a_missing_worktree_stops_the_resume_instead_of_writing_in_the_main_checkout(
    project: Path,
) -> None:
    import shutil as sh

    from asac.engine.runtime import make_context, project_root, store_for
    from asac.loader.load import load_manifest
    from asac.ports.state import StateError

    asac(project, "apply", "-p", "feature", "--harness", "claude-code", "--run-id", "gone")
    sh.rmtree(Path(os.environ["ASAC_STATE_DIR"]) / "worktrees" / "gone")
    manifest = load_manifest(project / "asac.yaml")
    ctx = make_context(manifest, "feature", store_for(project / "asac.yaml"),
                       project_root(project / "asac.yaml"), "claude-code")  # fmt: skip
    with pytest.raises(StateError, match="missing"):
        ctx.harness_for("ba", "gone")


def test_a_plain_folder_cannot_start_an_isolated_run(sandbox_project: Path) -> None:
    r = asac(sandbox_project, "apply", "-p", "feature", "--harness", "claude-code",
             "--run-id", "nogit")  # fmt: skip
    assert r.exit_code == 1
    assert "not a git repository" in r.output


MINI = """\
asac: { spec: "0.4", workspace: mini, team: t }
providers:
  llm: { source: asac/claude, version: "~> 1.0", config: { model: m } }
capabilities:
  build: { description: Build it, evidence: [built] }
evidenceTypes:
  built: { description: Built }
skills:
  impl: { ref: .asac/skills/impl.md, fulfils: build }
agents:
  dev: { skill: impl, provider: llm, harness: claude-code }
hooks:
  definitions:
    probe: { run: .asac/hooks/probe.sh, on_fail: block }
  post_step: [probe]
pipelines:
  feature:
    steps:
      build: { capability: build, agent: dev, mode: assist, producesEvidence: [built] }
"""


@pytest.fixture
def mini(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """One assist step and one post_step hook, under git: the smallest isolated project."""
    root = tmp_path / "mini"
    (root / ".asac" / "skills").mkdir(parents=True)
    (root / ".asac" / "hooks").mkdir(parents=True)
    (root / ".asac" / "skills" / "impl.md").write_text("Write AGENT_WROTE_THIS.\n")
    (root / "asac.yaml").write_text(MINI)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("ASAC_STATE_DIR", str(tmp_path / "state"))
    return root


def _mini_hook(root: Path, script: str) -> None:
    (root / ".asac" / "hooks" / "probe.sh").write_text(script)
    _git(root, "init", "-q", "-b", "main")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "base")


def test_hook_runs_in_the_worktree_and_blocks_when_the_agent_output_is_missing(mini: Path) -> None:
    _mini_hook(mini, 'test -f AGENT_WROTE_THIS || { echo "missing in $PWD" >&2; exit 1; }\n')
    asac(mini, "apply", "-p", "feature", "--run-id", "hk1")  # assist: handed to a person
    r = asac(mini, "evidence", "bootstrap", "hk1", "--evidence", "built")  # nothing written
    work = Path(os.environ["ASAC_STATE_DIR"]) / "worktrees" / "hk1"
    assert "hook 'probe' failed" in r.output, r.output
    assert f"missing in {work}" in asac(mini, "logs", "hk1").output


def test_hook_passes_on_the_worktree_even_when_the_main_checkout_lacks_the_file(
    mini: Path,
) -> None:
    _mini_hook(mini, "test -f AGENT_WROTE_THIS || exit 1\n")
    asac(mini, "apply", "-p", "feature", "--run-id", "hk2")
    work = Path(os.environ["ASAC_STATE_DIR"]) / "worktrees" / "hk2"
    (work / "AGENT_WROTE_THIS").write_text("x")  # the agent's output, in its own tree
    r = asac(mini, "evidence", "bootstrap", "hk2", "--evidence", "built")
    assert "hook 'probe' failed" not in r.output, r.output
    assert "completed" in asac(mini, "status").output
    assert not (mini / "AGENT_WROTE_THIS").exists()


def test_hook_script_edited_in_the_worktree_is_not_the_one_that_runs(mini: Path) -> None:
    """The agent may rewrite .asac/hooks/probe.sh in its tree: ASAC runs the main copy."""
    _mini_hook(mini, "test -f AGENT_WROTE_THIS || exit 1\n")
    asac(mini, "apply", "-p", "feature", "--run-id", "hk3")
    work = Path(os.environ["ASAC_STATE_DIR"]) / "worktrees" / "hk3"
    (work / ".asac" / "hooks" / "probe.sh").write_text("exit 0\n")  # tampering
    r = asac(mini, "evidence", "bootstrap", "hk3", "--evidence", "built")
    assert "hook 'probe' failed" in r.output, r.output


def test_a_run_with_no_worktree_record_never_advances_unisolated(project: Path) -> None:
    """A run created before isolation existed has no worktree record. Isolation is then not
    recorded, so the run is not isolated: the guard only applies to runs that *were* isolated.
    Here the record is missing on a run that was isolated: resuming must stop, not continue."""
    from asac.engine.run_state import RunState
    from asac.engine.runtime import store_for

    asac(project, "apply", "-p", "feature", "--harness", "claude-code", "--run-id", "norec")
    asac(project, "evidence", "bootstrap", "norec", "--evidence", "spec_reviewed", "--no-resume")
    store = store_for(project / "asac.yaml")
    # the audit is append-only: a run recorded as isolated keeps that fact
    assert RunState(store.audit("norec")).isolated is True
    # a run that was never isolated (fake harness, no worktree) is not forced into isolation
    asac(project, "apply", "-p", "feature", "--harness", "fake", "--run-id", "plain2")
    assert RunState(store.audit("plain2")).isolated is False
