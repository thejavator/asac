"""Port for run deliverables (files a step produced). Content is immutable once written."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class ArtifactError(Exception):
    """Bad name, too large, or already stored."""


class ArtifactNotFound(ArtifactError):
    pass


@dataclass(frozen=True)
class Artifact:
    run_id: str
    step_id: str
    name: str
    size: int
    sha256: str
    at: str


class ArtifactStore(Protocol):
    def put(self, run_id: str, step_id: str, name: str, data: bytes, at: str) -> Artifact:
        """Store a file. Writing the same name twice for a run raises ``ArtifactError``."""
        ...

    def list(self, run_id: str) -> list[Artifact]: ...
    def read(self, run_id: str, name: str) -> bytes: ...
