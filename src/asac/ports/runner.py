"""Port for ``mode: delegate`` execution (container, CI runner, ...)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ExecResult:
    """What a command printed inside the runner. ``exit_code`` 124 means it timed out."""

    exit_code: int
    stdout: str = ""
    stderr: str = ""


class Runner(Protocol):
    """Where a delegate step runs. ``available`` lets the engine apply ``fallback: assist``."""

    def available(self) -> bool: ...
    def start(self, run_id: str, step_id: str) -> str: ...
    def exec(self, handle: str, argv: list[str], timeout: int) -> ExecResult: ...
    def stop(self, handle: str) -> None: ...
