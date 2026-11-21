"""Per-run git worktree: the agent works in its own checkout, never in the main repository."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from asac.engine.workspace import WorkspaceError, create_workspace, remove_workspace


def _git(cwd: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )
    return proc.stdout.strip()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    if shutil.which("git") is None:
        pytest.skip("git is not installed")
    root = tmp_path / "project"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    (root / "app.py").write_text("print('hi')\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "base")
    return root


def test_creates_a_worktree_on_a_branch_named_after_the_run(repo: Path, tmp_path: Path) -> None:
    ws = create_workspace(repo, tmp_path / "state", "run_1")
    assert ws.path.is_dir() and (ws.path / "app.py").read_text() == "print('hi')\n"
    assert ws.branch == "asac/run_1"
    assert _git(ws.path, "rev-parse", "--abbrev-ref", "HEAD") == "asac/run_1"


def test_writes_in_the_worktree_do_not_touch_the_main_checkout(repo: Path, tmp_path: Path) -> None:
    ws = create_workspace(repo, tmp_path / "state", "run_1")
    (ws.path / "app.py").write_text("changed\n", encoding="utf-8")
    assert (repo / "app.py").read_text(encoding="utf-8") == "print('hi')\n"
    assert _git(repo, "status", "--porcelain") == ""


def test_worktree_starts_from_head_not_from_uncommitted_edits(repo: Path, tmp_path: Path) -> None:
    (repo / "app.py").write_text("uncommitted\n", encoding="utf-8")
    ws = create_workspace(repo, tmp_path / "state", "run_1")
    assert (ws.path / "app.py").read_text(encoding="utf-8") == "print('hi')\n"


def test_creating_twice_for_the_same_run_is_refused(repo: Path, tmp_path: Path) -> None:
    create_workspace(repo, tmp_path / "state", "run_1")
    with pytest.raises(WorkspaceError, match="already exists"):
        create_workspace(repo, tmp_path / "state", "run_1")


def test_refuses_a_project_that_is_not_a_git_repository(tmp_path: Path) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    (plain / "a.txt").write_text("x", encoding="utf-8")
    with pytest.raises(WorkspaceError, match="not a git repository"):
        create_workspace(plain, tmp_path / "state", "run_1")


def test_refuses_an_unsafe_run_id(repo: Path, tmp_path: Path) -> None:
    with pytest.raises(WorkspaceError, match="unsafe"):
        create_workspace(repo, tmp_path / "state", "../escape")


def test_remove_deletes_the_worktree_and_keeps_the_branch(repo: Path, tmp_path: Path) -> None:
    ws = create_workspace(repo, tmp_path / "state", "run_1")
    remove_workspace(repo, ws.path, ws.branch)
    assert not ws.path.exists()
    assert "asac/run_1" in _git(repo, "branch", "--list", "asac/run_1")


def test_remove_refuses_a_path_that_is_not_a_worktree_of_the_project(
    repo: Path, tmp_path: Path
) -> None:
    outside = tmp_path / "not-a-worktree"
    outside.mkdir()
    with pytest.raises(WorkspaceError, match="not a worktree"):
        remove_workspace(repo, outside, "asac/run_1")
    assert outside.is_dir()


def test_a_step_commit_leaves_out_build_artefacts_and_asac_state(
    repo: Path, tmp_path: Path
) -> None:
    """The branch is what a person reviews and merges: bytecode and ASAC's own files stay out."""
    from asac.engine.workspace import commit_step

    ws = create_workspace(repo, tmp_path / "state", "run_1")
    (ws.path / "feature.py").write_text("x = 1\n", encoding="utf-8")
    (ws.path / "__pycache__").mkdir()
    (ws.path / "__pycache__" / "feature.cpython-313.pyc").write_bytes(b"\x00")
    (ws.path / "sub" / "__pycache__").mkdir(parents=True)
    (ws.path / "sub" / "__pycache__" / "m.pyc").write_bytes(b"\x00")
    (ws.path / ".asac-state").mkdir()
    (ws.path / ".asac-state" / "scope.sha").write_text("abc", encoding="utf-8")
    commit_step(ws.path, "run_1", "build")
    files = _git(ws.path, "show", "--name-only", "--format=", "HEAD").splitlines()
    assert files == ["feature.py"]
