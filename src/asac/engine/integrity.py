"""Integrity of the rules an agent is judged by.

Before a tool runs, ASAC fingerprints the manifest, the variables and the ``.asac`` folder of the
main checkout (hooks, policies, skills, instructions). After it ran, it compares. An agent that
edits, deletes or adds a rule is caught here even when no OS sandbox is in place, and the step
never reaches a human gate as if it were clean.

Only the rules are covered. The code the agent produces is its job, and is judged by the rules.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

RULE_FILES = ("asac.yaml", "asac.vars.yaml")
RULE_DIRS = (".asac",)


def _digest(path: Path) -> str:
    if path.is_symlink():
        return "symlink:" + str(path.readlink())  # a link is recorded, never followed
    return hashlib.sha256(path.read_bytes()).hexdigest()


def snapshot(root: Path) -> dict[str, str]:
    """Relative path -> fingerprint, for every rule file under ``root``."""
    out: dict[str, str] = {}
    for name in RULE_FILES:
        p = root / name
        if p.is_file() or p.is_symlink():
            out[name] = _digest(p)
    for d in RULE_DIRS:
        base = root / d
        if not base.is_dir():
            continue
        for p in sorted(base.rglob("*")):
            if p.is_symlink() or p.is_file():
                out[p.relative_to(root).as_posix()] = _digest(p)
    return out


def changed(before: dict[str, str], after: dict[str, str]) -> list[str]:
    """Paths edited, deleted or added between two snapshots, sorted."""
    return sorted(
        path for path in before.keys() | after.keys() if before.get(path) != after.get(path)
    )
