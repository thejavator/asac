"""Per-run workspace: a git worktree on its own branch, where the agent does its work.

The main checkout keeps the manifest, the hooks, the policies and the state. The agent only
ever writes in the worktree, so a rule it could edit in its own checkout cannot be used to
approve its own work. The worktree starts from ``HEAD``: uncommitted local edits are not part
of what the agent is asked to change.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

_SAFE_RUN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,80}$")


# What a step commit never contains: the branch is what a person reviews and merges. Bytecode is
# a build artefact, and .asac-state holds ASAC's own bookkeeping (never the agent's work).
EXCLUDE_FROM_COMMIT = (
    ":(exclude).asac-state",
    ":(exclude)**/__pycache__",
    ":(exclude)*.pyc",
)


class WorkspaceError(Exception):
    pass


@dataclass(frozen=True)
class Workspace:
    run_id: str
    path: Path
    branch: str
    base: str  # sha of HEAD when the worktree was created: the starting point of the run


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    if shutil.which("git") is None:
        raise WorkspaceError("git is not installed (a run needs git to create its worktree)")
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=False, timeout=120
    )


# Options that make git ignore every setting an agent could plant in a repository it can write:
# a monitor or hook command, a pager, an external diff. They go on each call made on a worktree.
_NO_EXEC = (
    "-c", "core.fsmonitor=false",
    "-c", "core.hooksPath=/dev/null",
    "-c", "core.pager=cat",
    "-c", "diff.external=",
    "-c", "protocol.allow=never",
)  # fmt: skip


def real_gitdir(root: Path, path: Path) -> Path:
    """The git directory of the worktree at ``path``, read from the main repository.

    A worktree's ``.git`` is a file inside the folder the agent writes: it can point anywhere. The
    answer must come from the main repository, which the agent cannot write. It is the folder
    ``<main>/.git/worktrees/<name>``, and nothing else is accepted.
    """
    listed = _git(root, "worktree", "list", "--porcelain")
    here: str | None = None
    for line in listed.stdout.splitlines():
        if line.startswith("worktree "):
            here = line.removeprefix("worktree ")
        elif line == "" and here is not None:
            here = None
        if here is not None and Path(here).resolve() == path.resolve():
            common = _git(root, "rev-parse", "--git-common-dir").stdout.strip()
            common_dir = (
                (root / common).resolve() if not Path(common).is_absolute() else Path(common)
            )
            gitdir = common_dir / "worktrees" / Path(here).name
            if gitdir.is_dir():
                return gitdir
    raise WorkspaceError(f"{path} is not a worktree of this project")


def git_in_worktree(root: Path, path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run git on a worktree without trusting anything the agent wrote there."""
    gitdir = real_gitdir(root, path)
    return _git(path, "--git-dir", str(gitdir), "--work-tree", str(path), *_NO_EXEC, *args)


def _is_repo(root: Path) -> bool:
    proc = _git(root, "rev-parse", "--is-inside-work-tree")
    return proc.returncode == 0 and proc.stdout.strip() == "true"


def workspace_path(state_dir: Path, run_id: str) -> Path:
    return state_dir / "worktrees" / run_id


def create_workspace(root: Path, state_dir: Path, run_id: str) -> Workspace:
    """Create ``state_dir/worktrees/<run_id>`` on the new branch ``asac/<run_id>``."""
    if not _SAFE_RUN.match(run_id):
        raise WorkspaceError(f"unsafe run id '{run_id}' (letters, digits, '.', '_' or '-')")
    if not _is_repo(root):
        raise WorkspaceError(f"{root} is not a git repository: a run needs one to isolate work")
    path = workspace_path(state_dir, run_id)
    branch = f"asac/{run_id}"
    if path.exists():
        raise WorkspaceError(f"workspace for run '{run_id}' already exists at {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    proc = _git(root, "worktree", "add", "-q", "-b", branch, str(path), "HEAD")
    if proc.returncode != 0:
        raise WorkspaceError(f"git worktree add failed: {proc.stderr.strip()}")
    base = _git(path, "rev-parse", "HEAD").stdout.strip()
    return Workspace(run_id, path, branch, base)


def open_workspace(state_dir: Path, run_id: str, base: str) -> Workspace:
    """The worktree of an existing run (``--resume``). Never creates one.

    ``base`` is the sha recorded in the audit when the run was created: it is not recomputed.
    """
    if not _SAFE_RUN.match(run_id):
        raise WorkspaceError(f"unsafe run id '{run_id}' (letters, digits, '.', '_' or '-')")
    path = workspace_path(state_dir, run_id)
    if not path.is_dir() or not _is_repo(path):
        raise WorkspaceError(f"the worktree of run '{run_id}' is missing ({path})")
    head = _git(path, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    if head != f"asac/{run_id}":
        raise WorkspaceError(f"the worktree of run '{run_id}' is on '{head}', not asac/{run_id}")
    return Workspace(run_id, path, head, base)


def remove_workspace(root: Path, path: Path, branch: str) -> None:
    """Remove a worktree created by ASAC. The branch is kept: it holds the work to review."""
    listed = _git(root, "worktree", "list", "--porcelain")
    known = {
        Path(line.removeprefix("worktree ")).resolve()
        for line in listed.stdout.splitlines()
        if line.startswith("worktree ")
    }
    if path.resolve() not in known:
        raise WorkspaceError(f"{path} is not a worktree of this project")
    proc = _git(root, "worktree", "remove", "--force", str(path))
    if proc.returncode != 0:
        raise WorkspaceError(f"git worktree remove failed: {proc.stderr.strip()}")


def commit_step(root: Path, workdir: Path, run_id: str, step_id: str) -> str:
    """Make the commit the gate will approve, and return its sha.

    ASAC always writes that commit, so the approved sha is one ASAC created: never a commit the
    agent made, even when the agent committed everything itself. If there is nothing new, an
    empty commit records that the step was checked at this point.

    Git runs on the real git directory read from ``root``, never on the worktree's own ``.git``
    file, which the agent can rewrite to point at a repository whose configuration runs a command.
    """
    if not workdir.is_dir():
        raise WorkspaceError(f"{workdir} is not a worktree")

    def git(*a: str) -> subprocess.CompletedProcess[str]:
        return git_in_worktree(root, workdir, *a)

    git("add", "-A", "--", ".", *EXCLUDE_FROM_COMMIT)
    dirty = git("diff", "--cached", "--quiet").returncode != 0
    msg = f"asac: {step_id} (run {run_id})"
    args = ["-c", "user.name=ASAC", "-c", "user.email=asac@localhost",
            "commit", "-q", "--no-verify", "-m", msg]  # fmt: skip
    if not dirty:
        args.insert(args.index("-q"), "--allow-empty")
    proc = git(*args)
    if proc.returncode != 0:
        raise WorkspaceError(f"commit failed: {proc.stderr.strip()}")
    return git("rev-parse", "HEAD").stdout.strip()
