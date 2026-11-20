"""SQLite adapter for :class:`asac.ports.admin.AdminStore` (portal-admin.db, WAL)."""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path

from asac.ports.admin import AdminEvent, Mapping, UserRecord


class SqliteAdminStore:
    def __init__(self, path: Path | str) -> None:
        self._lock = threading.Lock()  # FastAPI runs sync handlers in a thread pool
        self._db = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        self._db.execute("PRAGMA journal_mode=WAL")
        with self._lock:
            self._db.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    subject TEXT PRIMARY KEY, name TEXT, claims TEXT, last_login TEXT);
                CREATE TABLE IF NOT EXISTS group_role_map (
                    claim TEXT, project_id TEXT, role TEXT,
                    PRIMARY KEY (claim, project_id, role));
                CREATE TABLE IF NOT EXISTS admin_audit (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT, actor TEXT,
                    action TEXT, detail TEXT);
                """
            )

    def record_login(self, subject: str, name: str, claims: list[str], at: str) -> None:
        with self._lock:
            self._db.execute(
                "INSERT INTO users VALUES (?, ?, ?, ?) ON CONFLICT(subject) DO UPDATE SET "
                "name = excluded.name, claims = excluded.claims, last_login = excluded.last_login",
                (subject, name, json.dumps(sorted(claims)), at),
            )

    def list_users(self) -> list[UserRecord]:
        with self._lock:
            rows = self._db.execute(
                "SELECT subject, name, claims, last_login FROM users ORDER BY last_login DESC"
            ).fetchall()
        return [UserRecord(s, n, tuple(json.loads(c)), at) for s, n, c, at in rows]

    def list_mappings(self, project_id: str | None = None) -> list[Mapping]:
        sql = "SELECT claim, project_id, role FROM group_role_map"
        args: tuple[str, ...] = ()
        if project_id is not None:
            sql += " WHERE project_id = ?"
            args = (project_id,)
        with self._lock:
            rows = self._db.execute(sql + " ORDER BY project_id, claim, role", args).fetchall()
        return [Mapping(*r) for r in rows]

    def add_mapping(self, mapping: Mapping) -> bool:
        with self._lock:
            cur = self._db.execute(
                "INSERT OR IGNORE INTO group_role_map VALUES (?, ?, ?)",
                (mapping.claim, mapping.project_id, mapping.role),
            )
        return cur.rowcount == 1

    def remove_mapping(self, mapping: Mapping) -> bool:
        with self._lock:
            cur = self._db.execute(
                "DELETE FROM group_role_map WHERE claim = ? AND project_id = ? AND role = ?",
                (mapping.claim, mapping.project_id, mapping.role),
            )
        return cur.rowcount == 1

    def append_event(self, actor: str, action: str, at: str, detail: str) -> None:
        with self._lock:
            self._db.execute(
                "INSERT INTO admin_audit (at, actor, action, detail) VALUES (?, ?, ?, ?)",
                (at, actor, action, detail),
            )

    def events(self) -> list[AdminEvent]:
        with self._lock:
            rows = self._db.execute(
                "SELECT seq, at, actor, action, detail FROM admin_audit ORDER BY seq DESC"
            ).fetchall()
        return [AdminEvent(*r) for r in rows]
