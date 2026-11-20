"""Port for pipeline drafts: edits kept by the portal until they are proposed through git.

A draft never writes to git. It records the commit it was based on and the exact base content,
so a later proposal can tell whether the default branch changed the same file.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

DRAFT_STATUSES = frozenset({"draft", "proposed", "applied", "closed"})


@dataclass(frozen=True)
class Draft:
    id: str
    project_id: str
    path: str
    base_sha: str
    base_content: str
    content: str
    status: str  # draft | proposed | applied | closed
    author_sub: str
    author_name: str
    author_email: str
    created_at: str
    updated_at: str
    branch: str | None = None
    cr_id: str | None = None
    cr_url: str | None = None


class DraftStore(Protocol):
    def create(self, draft: Draft) -> None: ...
    def get(self, project_id: str, draft_id: str) -> Draft | None: ...
    def list(self, project_id: str) -> list[Draft]: ...
    def update(self, draft: Draft) -> None: ...
