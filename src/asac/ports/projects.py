"""Port for the projects a portal serves (database, a service catalogue...).

A project is one repository with one ``asac.yaml``. The manifest stays in the repository and
remains the source of truth; the registry only says where it is and who may see it. Projects
are created, edited and archived through the registry, never by editing a file.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

PROJECT_ID = re.compile(r"^[a-z][a-z0-9-]{0,40}$")


@dataclass(frozen=True)
class Project:
    id: str
    name: str
    manifest: Path
    team: str | None = None
    repo: str | None = None
    #: claim values allowed to see the project; empty means anyone signed in
    access: frozenset[str] = frozenset()
    archived: bool = False


@dataclass(frozen=True)
class Directory:
    organization: str
    #: claim values that see every project (managers, auditors)
    org_roles: frozenset[str]
    projects: tuple[Project, ...]


class ProjectError(Exception):
    """A refused change: unknown project, duplicate id, invalid value."""


class ProjectRegistry(Protocol):
    def load(self, include_archived: bool = False) -> Directory: ...
    def create(self, project: Project) -> None:
        """Raises :class:`ProjectError` when the id already exists."""
        ...

    def update(self, project: Project) -> None:
        """Replaces name, manifest, team, repo and access. Raises when the id is unknown."""
        ...

    def set_archived(self, project_id: str, archived: bool) -> None: ...
    def set_organization(self, name: str, org_roles: frozenset[str]) -> None: ...
