"""Shared pieces for harness adapters."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from asac.model import Manifest


class HarnessError(Exception):
    """The harness cannot do what was asked (wrong mode, not implemented, bad name)."""


@dataclass(frozen=True)
class AdapterContext:
    root: Path  # the main checkout: manifest, hooks, policies, skill sources (read only here)
    manifest: Manifest
    state_dir: Path
    autorun: bool = False  # launch the tool CLI on assist steps (asac.vars.yaml: autorun)
    autorun_timeout: int = 900
    # Where the agent writes (skills, CLAUDE.md, .mcp.json, brief, its own edits). The run's
    # worktree when isolation is on; otherwise the main checkout, as before.
    work: Path | None = None
    # Run the tool inside the OS sandbox (srt) with the policy derived from the run.
    sandbox: bool = False
    sandbox_domains: tuple[str, ...] = ()

    @property
    def workdir(self) -> Path:
        return self.work if self.work is not None else self.root


_SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def safe_name(name: str) -> str:
    """Names become directory or file names, so refuse anything that could escape."""
    if not _SAFE_NAME.match(name) or ".." in name:
        raise HarnessError(f"unsafe name '{name}' (use letters, digits, '.', '_' or '-')")
    return name


def write_brief(ctx: AdapterContext, run_id: str, step: str, text: str) -> Path:
    path = ctx.state_dir / "briefs" / safe_name(run_id) / f"{safe_name(step)}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    # A loop sends the reason a turn was rejected back to the agent. The brief is regenerated at
    # every launch, so the feedback lives in its own file and is appended each time.
    feedback = path.with_name(f"{safe_name(step)}.feedback.md")
    if feedback.is_file():
        text = text.rstrip("\n") + "\n" + feedback.read_text(encoding="utf-8")
    path.write_text(text, encoding="utf-8")
    return path
