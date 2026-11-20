"""Port for an issue tracker: look up the ticket a run came from and link to it.

Adapters: Jira (Cloud and Data Center), GitHub issues, GitLab issues. Read-only for now: the
portal shows the ticket and links to it; writing back (comments, transitions) is a later step.
Credentials are resolved from a vault reference by the factory, never passed by callers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class TrackerError(Exception):
    """Any failure talking to the tracker. The message never contains a credential."""


class NotFound(TrackerError):
    pass


@dataclass(frozen=True)
class Issue:
    key: str  # PAY-139 for Jira, 12 for GitHub and GitLab
    title: str
    status: str  # as the tracker names it (To Do, open, closed...)
    url: str  # page a person opens in a browser
    type: str = ""
    labels: tuple[str, ...] = ()


class Tracker(Protocol):
    @property
    def name(self) -> str:
        """Display name: Jira, GitHub or GitLab."""
        ...

    @property
    def provider(self) -> str:
        """Trigger provider this tracker answers for (``jira``, ``github``, ``gitlab``)."""
        ...

    def valid_key(self, key: str) -> bool: ...
    def issue_url(self, key: str) -> str:
        """Browser link, computed without a network call. Raises NotFound for a bad key."""
        ...

    def get_issue(self, key: str) -> Issue: ...
