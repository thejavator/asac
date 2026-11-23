"""OS sandbox for delegate and autorun steps: ``srt`` (Anthropic sandbox-runtime).

The agent may write only in its worktree, may not read the secrets it is not meant to read,
and may reach only the domains it was given. Everything is refused unless listed here.
The policy is built from the manifest and the run, never from what the agent asks for.
"""

from __future__ import annotations

import re
import shlex
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Pinned to the version validated in the spike (srt 0.0.83). A different version is a new spike.
SRT_VERSION = "0.0.83"


class SandboxError(Exception):
    """The policy is unsafe or incomplete: the step must not run."""


@dataclass(frozen=True)
class SandboxPolicy:
    workdir: Path  # the run's worktree: the only place the agent may write
    allowed_domains: tuple[str, ...] = ()  # exact hostnames; no wildcard
    extra_write: tuple[str, ...] = ()  # scratch paths the tool itself needs
    deny_read: tuple[str, ...] = ("~/.ssh", "~/.aws", "~/.gnupg")


def _check(policy: SandboxPolicy) -> None:
    if not policy.workdir.is_absolute():
        raise SandboxError(f"the sandbox needs an absolute workdir, got '{policy.workdir}'")
    for d in policy.allowed_domains:
        if "*" in d:
            raise SandboxError(f"wildcard domain '{d}' is refused: list exact hosts")
        if not d or d.startswith(".") or "/" in d or " " in d:
            raise SandboxError(f"invalid domain '{d}'")


def build_settings(policy: SandboxPolicy) -> dict[str, Any]:
    """The srt settings file for this step. Every key srt requires is present."""
    _check(policy)
    return {
        "network": {
            "allowedDomains": list(policy.allowed_domains),
            "deniedDomains": [],  # required by srt, even when empty
        },
        "filesystem": {
            "allowWrite": [str(policy.workdir), *policy.extra_write],
            "denyRead": list(policy.deny_read),
            "denyWrite": [],
        },
    }


def wrap_command(
    argv: Sequence[str],
    policy: SandboxPolicy,
    settings_path: Path,
    srt: str = "srt",
    debug: bool = False,
) -> list[str]:
    """``srt -s <settings> -c '<command>'``. The command is quoted: no argument can break out.

    ``debug`` makes srt log the network connections it refuses, so ASAC can audit them.
    """
    if not argv:
        raise SandboxError("nothing to run")
    return [srt, *(["-d"] if debug else []), "-s", str(settings_path), "-c", shlex.join(argv)]


MAX_DENIALS = 20  # an agent that probes in a loop must not fill the audit


@dataclass(frozen=True)
class Denial:
    kind: str  # "network" | "filesystem" | "more"
    target: str


# What the system says when it refuses. File refusals come from the refused program's own stderr
# (Operation not permitted); connection refusals from srt's log. Anything else is not a denial.
_NET = re.compile(r"No matching rule, denying: (\S+)")
# "<program or script>: [line N: ]<path>: Operation not permitted". The path is the last "/..."
# before the message; a program name or "line N" in front is not part of it.
_FS = re.compile(r"(?:^|: )(/[^:\n]*?): [Oo]peration not permitted\s*$")
_FS_ZSH = re.compile(r"[Oo]peration not permitted: (/\S+)\s*$")


def parse_denials(text: str) -> list[Denial]:
    """The refusals found in a sandboxed tool's captured output, each listed once, capped."""
    seen: set[tuple[str, str]] = set()
    found: list[Denial] = []
    for line in text.splitlines():
        kind, target = "", ""
        m = _NET.search(line)
        if m:
            kind, target = "network", m.group(1)
        else:
            f = _FS.search(line.strip()) or _FS_ZSH.search(line.strip())
            if f:
                kind, target = "filesystem", f.group(1)
        if kind and (kind, target) not in seen:
            seen.add((kind, target))
            found.append(Denial(kind, target))
    if len(found) > MAX_DENIALS:
        extra = len(found) - MAX_DENIALS
        found = [*found[:MAX_DENIALS], Denial("more", f"{extra} more not listed")]
    return found
