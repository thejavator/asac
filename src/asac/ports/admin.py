"""Port for portal administration state: users seen at sign-in, group -> project role mappings.

Mappings made in the portal live here and are added to the claims when roles are computed.
Every change is audited.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

#: roles a project mapping may grant (organisation roles are claims, not mappings)
PROJECT_ROLES = frozenset({"owner", "product_owner", "qa", "developer", "reader"})


@dataclass(frozen=True)
class UserRecord:
    subject: str
    name: str
    claims: tuple[str, ...]
    last_login: str


@dataclass(frozen=True)
class Mapping:
    claim: str
    project_id: str
    role: str


@dataclass(frozen=True)
class AdminEvent:
    seq: int
    at: str
    actor: str
    action: str
    detail: str


class AdminStore(Protocol):
    def record_login(self, subject: str, name: str, claims: list[str], at: str) -> None: ...
    def list_users(self) -> list[UserRecord]: ...
    def list_mappings(self, project_id: str | None = None) -> list[Mapping]: ...
    def add_mapping(self, mapping: Mapping) -> bool: ...
    def remove_mapping(self, mapping: Mapping) -> bool: ...
    def append_event(self, actor: str, action: str, at: str, detail: str) -> None: ...
    def events(self) -> list[AdminEvent]: ...
