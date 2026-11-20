"""Port for skill, module and hook registries (filesystem, OCI, ...)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Resolved:
    ref: str
    version: str
    digest: str
    path: str


class Registry(Protocol):
    def resolve(self, ref: str) -> Resolved: ...
    def search(self, query: str) -> list[str]: ...
    def publish(self, source_dir: str, ref: str) -> Resolved: ...
