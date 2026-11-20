"""Conformance suite for the ProjectRegistry port (SQLite adapter)."""

from pathlib import Path

import pytest

from asac.adapters.projects_sqlite import SqliteProjectRegistry
from asac.ports.projects import Project, ProjectError, ProjectRegistry


@pytest.fixture(params=["sqlite"])
def registry(request: pytest.FixtureRequest, tmp_path: Path) -> ProjectRegistry:
    return SqliteProjectRegistry(tmp_path / "p.db")


def proj(pid: str = "pay", **kw: object) -> Project:
    return Project(id=pid, name=kw.pop("name", "Pay"), manifest=Path("/x/asac.yaml"), **kw)  # type: ignore[arg-type]


def test_empty_directory_has_defaults(registry: ProjectRegistry) -> None:
    d = registry.load()
    assert d.projects == () and d.organization == "Organization" and d.org_roles == frozenset()


def test_create_list_and_duplicate(registry: ProjectRegistry) -> None:
    registry.create(proj("a", access=frozenset({"x"}), team="T", repo="r"))
    registry.create(proj("b"))
    d = registry.load()
    assert [p.id for p in d.projects] == ["a", "b"]
    assert d.projects[0].access == frozenset({"x"}) and d.projects[0].team == "T"
    with pytest.raises(ProjectError):
        registry.create(proj("a"))


def test_update_and_unknown(registry: ProjectRegistry) -> None:
    registry.create(proj("a"))
    registry.update(proj("a", name="New", access=frozenset({"g"})))
    p = registry.load().projects[0]
    assert p.name == "New" and p.access == frozenset({"g"})
    with pytest.raises(ProjectError):
        registry.update(proj("zzz"))


def test_archive_hides_and_restore_shows(registry: ProjectRegistry) -> None:
    registry.create(proj("a"))
    registry.set_archived("a", True)
    assert registry.load().projects == ()
    assert registry.load(include_archived=True).projects[0].archived is True
    registry.set_archived("a", False)
    assert [p.id for p in registry.load().projects] == ["a"]
    with pytest.raises(ProjectError):
        registry.set_archived("zzz", True)


def test_organization_roundtrip(registry: ProjectRegistry) -> None:
    registry.set_organization("Acme", frozenset({"auditor"}))
    registry.set_organization("Acme 2", frozenset({"manager", "auditor"}))
    d = registry.load()
    assert d.organization == "Acme 2" and d.org_roles == frozenset({"manager", "auditor"})
