"""Local hooks (``run:``). Contract: exit 0 = pass, anything else = fail.

Trust rules: a hook runs only if it is declared in the manifest and its path stays
inside the repository. Hooks are never discovered on disk. ``ref:`` hooks need the
registry (not implemented yet) and are refused with a clear error.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from asac.model import Manifest

TIMEOUT_SECONDS = 60
# Nothing from the caller's environment leaks into a hook except these.
_PASS_ENV = ("PATH", "LANG", "LC_ALL", "TMPDIR")


class HookError(Exception):
    """The hook is misconfigured or untrusted. Never silently skipped."""


@dataclass(frozen=True)
class HookResult:
    name: str
    passed: bool
    on_fail: str
    output: str


def resolve_hook_path(root: Path, run: str) -> Path:
    base = root.resolve()
    path = (base / run).resolve()
    if not path.is_relative_to(base):
        raise HookError(f"hook path '{run}' is outside the repository")
    if not path.is_file():
        raise HookError(f"hook script '{run}' not found")
    return path


def run_hook(
    manifest: Manifest,
    root: Path,
    name: str,
    stdin: str = "",
    env: dict[str, str] | None = None,
    workdir: Path | None = None,
) -> HookResult:
    """Run a declared hook. The script is always read from ``root`` (the main checkout), so an
    agent cannot rewrite the check it is judged by. It runs in ``workdir`` (the run's worktree,
    where the agent's output is); without one, in ``root``.
    """
    hooks = manifest.hooks
    if hooks is None or name not in hooks.definitions:
        raise HookError(f"hook '{name}' is not declared in the manifest")
    d = hooks.definitions[name]
    if d.run is None:
        raise HookError(f"hook '{name}' uses 'ref', which needs the registry (not implemented)")
    script = resolve_hook_path(root, d.run)
    clean = {k: os.environ[k] for k in _PASS_ENV if k in os.environ}
    clean.update(env or {})
    try:
        proc = subprocess.run(
            ["/bin/sh", str(script)],
            input=stdin,
            capture_output=True,
            text=True,
            cwd=workdir if workdir is not None else root,
            env=clean,
            timeout=TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return HookResult(name, False, d.on_fail, f"timed out after {TIMEOUT_SECONDS}s")
    out = (proc.stdout + proc.stderr).strip()
    return HookResult(name, proc.returncode == 0, d.on_fail, out)


def run_hooks(
    manifest: Manifest,
    root: Path,
    attach: str,
    stdin: str = "",
    env: dict[str, str] | None = None,
    workdir: Path | None = None,
) -> list[HookResult]:
    """Run every hook attached to ``pre_tool`` or ``post_step``, in declaration order."""
    if manifest.hooks is None:
        return []
    names = getattr(manifest.hooks, attach)
    return [run_hook(manifest, root, n, stdin, env, workdir) for n in names]


def run_hooks_named(
    manifest: Manifest,
    root: Path,
    name: str,
    env: dict[str, str] | None = None,
    workdir: Path | None = None,
) -> HookResult:
    """One declared hook by name, with the same trust rules as ``run_hook`` (used by loops)."""
    return run_hook(manifest, root, name, "", env, workdir)
