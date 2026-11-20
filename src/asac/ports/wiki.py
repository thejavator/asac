"""Port for a wiki: find the pages a run or a gate decision refers to and link to them.

Adapters: Confluence (Cloud and Data Center) and GitLab wikis. GitHub wikis have no API and
are not supported. Read-only; credentials come from a vault reference through the factory.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class WikiError(Exception):
    """Any failure talking to the wiki. The message never contains a credential."""


class NotFound(WikiError):
    pass


@dataclass(frozen=True)
class Page:
    id: str  # Confluence content id, GitLab slug
    title: str
    url: str


class Wiki(Protocol):
    @property
    def name(self) -> str:
        """Display name: Confluence or GitLab wiki."""
        ...

    def search(self, query: str, limit: int = 10) -> list[Page]:
        """Pages whose title contains ``query`` (case-insensitive), at most ``limit``."""
        ...

    def get_page(self, page_id: str) -> Page: ...
