"""What a person needs to see before they sign a gate: how urgent it is, and what was checked.

Everything here is read from the run's audit and the clock. Nothing is invented: a hook that left
no record is not listed, and an old audit that did not record when a hook ran says so (empty).
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from asac.clock import parse_ts
from asac.ports.state import AuditRecord

SOON_SECONDS = 24 * 3600  # a decision due within a day is "soon"


@dataclass(frozen=True)
class Check:
    kind: str  # "hook"
    name: str
    moment: str  # "pre_tool" | "post_step" | "" for an audit that did not record it
    passed: bool
    output: str


def urgency(timeout_at: str | None, now: str) -> tuple[str, int | None]:
    """("late" | "soon" | "none", seconds until due; negative when late)."""
    if not timeout_at:
        return "none", None
    left = int((parse_ts(timeout_at) - parse_ts(now)).total_seconds())
    if left < 0:
        return "late", left
    return ("soon" if left <= SOON_SECONDS else "none"), left


def checks_from_audit(rows: list[AuditRecord], step_id: str) -> list[Check]:
    """The hook results of one step, in the order they ran."""
    out: list[Check] = []
    for a in rows:
        if a.step_id != step_id or a.action not in ("hook.passed", "hook.failed"):
            continue
        head, _, output = a.detail.partition("\n")
        moment, _, name = head.partition(" ")
        if moment not in ("pre_tool", "post_step") or not name:
            moment, name = "", head  # recorded before the moment was written
        out.append(Check("hook", name, moment, a.action == "hook.passed", output.strip()))
    return out


def started_at(rows: list[AuditRecord]) -> str | None:
    return next((a.at for a in rows if a.action == "run.created"), None)


@dataclass(frozen=True)
class ChangedFile:
    path: str
    change: str  # added | modified | deleted | renamed
    mounted: bool = (
        False  # written by ASAC for the tool (skill, CLAUDE.md...), not the agent's work
    )


# What the harnesses mount in the worktree. Anchored paths: a CLAUDE.md in a subfolder, or a
# settings file, is not ASAC's and stays in the agent's own list.
_MOUNTS = re.compile(
    r"^(\.claude/skills/[^/]+/SKILL\.md|\.bob/skills/[^/]+/SKILL\.md|\.agent/skills/[^/]+/SKILL\.md"
    r"|\.cursor/rules/asac-[^/]+\.mdc|\.github/instructions/asac-[^/]+\.instructions\.md"
    r"|CLAUDE\.md|AGENTS\.md|\.mcp\.json)$"
)


def is_asac_mount(path: str) -> bool:
    return bool(_MOUNTS.match(path))


_SHA = re.compile(r"^[0-9a-f]{40}$")
_KINDS = {"A": "added", "M": "modified", "D": "deleted", "R": "renamed", "T": "modified"}
_NOT_WORK = (".asac-state/", "__pycache__/")  # ASAC's bookkeeping and bytecode are not the work


def changed_files(worktree: Path, sha: str) -> list[ChangedFile]:
    """The files the commit a gate approves changed, read from git. Empty if it cannot be read.

    ``sha`` comes from the database, but it is handed to git, so it must be a full commit id:
    anything else (an option, a ref name) is refused before git is run.
    """
    if not _SHA.match(sha) or not worktree.is_dir():
        return []
    try:
        proc = subprocess.run(
            ["git", "show", "--name-status", "--no-renames", "--format=", sha],
            cwd=worktree, capture_output=True, text=True, timeout=20, check=False,
        )  # fmt: skip
    except (OSError, subprocess.TimeoutExpired):
        return []
    if proc.returncode != 0:
        return []
    out: list[ChangedFile] = []
    for line in proc.stdout.splitlines():
        code, _, path = line.partition("\t")
        if not path or any(m in path for m in _NOT_WORK):
            continue
        out.append(ChangedFile(path, _KINDS.get(code[:1], "modified"), is_asac_mount(path)))
    return out
