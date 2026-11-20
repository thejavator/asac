"""Test helper: create the projects of a portal in its database from a small YAML description."""

from pathlib import Path

import yaml

from asac.adapters.admin_sqlite import SqliteAdminStore
from asac.adapters.projects_sqlite import SqliteProjectRegistry
from asac.ports.admin import Mapping
from asac.ports.projects import Project


def seed_portal(description: Path) -> Path:
    """Read ``description`` (organization, org_roles, projects[...roles]) and fill the portal DB."""
    raw = yaml.safe_load(description.read_text())
    data = description.parent / "portal-data"
    data.mkdir(exist_ok=True)
    registry = SqliteProjectRegistry(data / "portal-admin.db")
    if registry.load().projects:  # already seeded: several clients may share one portal folder
        return data
    admin = SqliteAdminStore(data / "portal-admin.db")
    registry.set_organization(
        raw.get("organization", "Organization"), frozenset(raw.get("org_roles", []))
    )
    for e in raw["projects"]:
        registry.create(
            Project(
                id=e["id"], name=e["name"], manifest=(description.parent / e["manifest"]).resolve(),
                team=e.get("team"), repo=e.get("repo"), access=frozenset(e.get("access", [])),
            )
        )  # fmt: skip
        for claim, roles in e.get("roles", {}).items():
            for role in roles:
                admin.add_mapping(Mapping(claim, e["id"], role))
    return data


def seed_single(data: Path, manifest: Path, project_id: str = "default") -> Path:
    """One project, as an operator would create it in the portal: ``data`` is the portal folder."""
    data.mkdir(parents=True, exist_ok=True)
    registry = SqliteProjectRegistry(data / "portal-admin.db")
    if not any(p.id == project_id for p in registry.load(include_archived=True).projects):
        registry.create(
            Project(id=project_id, name=manifest.parent.name, manifest=manifest.resolve())
        )
    return data
