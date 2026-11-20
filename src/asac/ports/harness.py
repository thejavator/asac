"""Port for ``asac/harness-interface@2.0`` (docs/concepts/harness.md)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class HarnessDescriptor:
    """Static runtime capabilities. ``describe()`` must return the same values."""

    id: str
    interactive: bool
    headless: bool
    mcp: bool
    streaming: bool


class Harness(Protocol):
    def mount(self, skill: str) -> None: ...
    def run(self, task: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]: ...
    def tools(self, mcp_servers: list[str]) -> None: ...
    def permissions(self, mode: str) -> None: ...
    def emit(self, event: dict[str, Any]) -> None: ...
    def describe(self) -> HarnessDescriptor: ...
    def health_check(self) -> bool: ...
