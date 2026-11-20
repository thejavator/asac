"""SQLite adapter for :class:`asac.ports.projects.ProjectRegistry` (portal-admin.db, WAL)."""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path

from asac.ports.projects import Directory, Project, ProjectError

_COLS = "id, name, manifest, team, repo, access, archived"


class SqliteProjectRegistry:
    def __init__(self, path: Path | str) -> None:
        self._lock = threading.Lock()
        self._db = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        self._db.execute("PRAGMA journal_mode=WAL")
        with self._lock:
            self._db.executescript(
                """
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL, manifest TEXT NOT NULL,
                    team TEXT, repo TEXT, access TEXT NOT NULL DEFAULT '[]',
                    archived INTEGER NOT NULL DEFAULT 0, seq INTEGER);
                CREATE TABLE IF NOT EXISTS organization (
                    id INTEGER PRIMARY KEY CHECK (id = 1), name TEXT NOT NULL,
                    org_roles TEXT NOT NULL);
                """
            )

    def load(self, include_archived: bool = False) -> Directory:
        with self._lock:
            rows = self._db.execute(
                f"SELECT {_COLS} FROM projects "
                + ("" if include_archived else "WHERE archived = 0 ")
                + "ORDER BY rowid"
            ).fetchall()
            org = self._db.execute("SELECT name, org_roles FROM organization").fetchone()
        name, roles = (
            (org[0], frozenset(json.loads(org[1]))) if org else ("Organization", frozenset())
        )
        projects = tuple(
            Project(
                id=i, name=n, manifest=Path(m), team=t, repo=r,
                access=frozenset(json.loads(a)), archived=bool(ar),
            )
            for i, n, m, t, r, a, ar in rows
        )  # fmt: skip
        return Directory(name, roles, projects)

    def create(self, project: Project) -> None:
        with self._lock:
            try:
                self._db.execute(
                    "INSERT INTO projects (id, name, manifest, team, repo, access) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (project.id, project.name, str(project.manifest), project.team,
                     project.repo, json.dumps(sorted(project.access))),
                )  # fmt: skip
            except sqlite3.IntegrityError:
                raise ProjectError(f"project {project.id} already exists") from None

    def update(self, project: Project) -> None:
        with self._lock:
            cur = self._db.execute(
                "UPDATE projects SET name=?, manifest=?, team=?, repo=?, access=? WHERE id=?",
                (project.name, str(project.manifest), project.team, project.repo,
                 json.dumps(sorted(project.access)), project.id),
            )  # fmt: skip
        if cur.rowcount != 1:
            raise ProjectError(f"unknown project {project.id}")

    def set_archived(self, project_id: str, archived: bool) -> None:
        with self._lock:
            cur = self._db.execute(
                "UPDATE projects SET archived=? WHERE id=?", (int(archived), project_id)
            )
        if cur.rowcount != 1:
            raise ProjectError(f"unknown project {project_id}")

    def set_organization(self, name: str, org_roles: frozenset[str]) -> None:
        with self._lock:
            self._db.execute(
                "INSERT INTO organization VALUES (1, ?, ?) ON CONFLICT(id) DO UPDATE SET "
                "name = excluded.name, org_roles = excluded.org_roles",
                (name, json.dumps(sorted(org_roles))),
            )
