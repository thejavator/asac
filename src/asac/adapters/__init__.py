"""Adapter selection. Adapters are looked up by name from configuration."""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path

from asac.adapters.base import AdapterContext, HarnessError
from asac.adapters.claude_code import ClaudeCodeHarness
from asac.adapters.fake_harness import FakeHarness
from asac.adapters.file_mount import (
    AntigravityHarness,
    BobHarness,
    CodexHarness,
    CopilotHarness,
    CursorHarness,
)
from asac.adapters.state_sqlite import SqliteStateStore
from asac.ports.harness import Harness
from asac.ports.state import StateStore


class AdapterNotAvailable(Exception):
    pass


HARNESS_ADAPTERS: dict[str, Callable[[AdapterContext], Harness]] = {
    "fake": FakeHarness,
    "claude-code": ClaudeCodeHarness,
    "codex": CodexHarness,
    "antigravity": AntigravityHarness,
    "copilot": CopilotHarness,
    "cursor": CursorHarness,
    "bob": BobHarness,
}


def harness_factory(name: str, ctx: AdapterContext) -> Harness:
    factory = HARNESS_ADAPTERS.get(name)
    if factory is None:
        available = ", ".join(sorted(HARNESS_ADAPTERS))
        raise AdapterNotAvailable(
            f"harness '{name}' has no adapter in this build (available: {available}); "
            "use --harness fake or claude-code"
        )
    return factory(ctx)


def harness_available(name: str) -> bool:
    return name in HARNESS_ADAPTERS


def state_dir(project_root: Path, project: str | None = None) -> Path:
    """Where SQLite state lives. With a shared ``ASAC_STATE_DIR``, each project gets a folder."""
    env = os.environ.get("ASAC_STATE_DIR")
    if env:
        return Path(env) / project if project else Path(env)
    return project_root / ".asac-state"


def open_state(project_root: Path, project: str | None = None) -> StateStore:
    """SQLite by default; ``ASAC_STATE_URL=postgresql://...`` selects the Postgres adapter.

    ``project`` (or ``ASAC_PROJECT``) separates the data of several projects that share one
    backend: a folder per project for SQLite, a schema per project for Postgres.
    """
    project = project or os.environ.get("ASAC_PROJECT") or None
    url = os.environ.get("ASAC_STATE_URL")
    if url:
        if not url.startswith(("postgresql://", "postgres://")):
            raise AdapterNotAvailable("ASAC_STATE_URL must start with postgresql://")
        try:
            from asac.adapters.state_postgres import PostgresStateStore
        except ImportError:
            raise AdapterNotAvailable(
                "the Postgres state store needs the 'postgres' extra "
                "(pip install 'asac-cli[postgres]')"
            ) from None
        schema = "asac_" + project.replace("-", "_") if project else None
        return PostgresStateStore(url, schema)
    return SqliteStateStore(state_dir(project_root, project) / "state.db")


__all__ = ["AdapterContext", "AdapterNotAvailable", "HarnessError", "harness_factory"]
