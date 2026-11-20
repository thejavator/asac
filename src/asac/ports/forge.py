"""Port for a code forge: read files, branches, commits and change requests (MR/PR).

The engine, API and portal import only this module. Adapters: generic ``git`` (any remote, no
change requests), then GitLab, GitHub, Gitea/Forgejo, Bitbucket, Azure DevOps. Credentials are
never arguments: an adapter reads them from a vault reference at construction time.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class ForgeError(Exception):
    """Any failure talking to the forge. The message never contains a credential."""


class NotFound(ForgeError):
    pass


class Conflict(ForgeError):
    """The branch moved since ``base_sha``: the caller must rebase its draft."""

    def __init__(self, message: str, current_sha: str) -> None:
        super().__init__(message)
        self.current_sha = current_sha


class Unsupported(ForgeError):
    """The forge has no such feature (for example change requests on plain git)."""


@dataclass(frozen=True)
class FileContent:
    path: str
    content: str
    commit: str  # sha of the branch head the content was read at


@dataclass(frozen=True)
class Author:
    name: str
    email: str


@dataclass(frozen=True)
class ChangeRequest:
    id: str
    url: str
    source_branch: str
    target_branch: str
    state: str  # open | merged | closed
    author: str


@dataclass(frozen=True)
class Capabilities:
    change_requests: bool
    members: bool
    webhooks: bool


class Forge(Protocol):
    def capabilities(self) -> Capabilities: ...
    def default_branch(self) -> str: ...
    def head(self, branch: str) -> str: ...
    def read_file(self, path: str, branch: str | None = None) -> FileContent: ...
    def create_branch(self, name: str, from_sha: str) -> None: ...
    def commit_files(
        self, branch: str, files: dict[str, str], message: str, author: Author, base_sha: str
    ) -> str:
        """Write files on ``branch`` and return the new head. Raises Conflict if the branch
        head is not ``base_sha``. Never force-pushes."""
        ...

    def open_change_request(
        self, source: str, target: str, title: str, description: str
    ) -> ChangeRequest: ...
    def get_change_request(self, cr_id: str) -> ChangeRequest: ...
