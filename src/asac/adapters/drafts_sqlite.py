"""SQLite adapter for :class:`asac.ports.drafts.DraftStore` (portal-admin.db, WAL)."""

from __future__ import annotations

import sqlite3
import threading
from dataclasses import astuple, fields
from pathlib import Path

from asac.ports.drafts import Draft

_COLS = [f.name for f in fields(Draft)]


class SqliteDraftStore:
    def __init__(self, path: Path | str) -> None:
        self._lock = threading.Lock()
        self._db = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        self._db.execute("PRAGMA journal_mode=WAL")
        with self._lock:
            self._db.execute(
                f"CREATE TABLE IF NOT EXISTS pipeline_drafts ({', '.join(_COLS)}, "
                "PRIMARY KEY (project_id, id))"
            )

    def create(self, draft: Draft) -> None:
        marks = ", ".join("?" * len(_COLS))
        with self._lock:
            self._db.execute(f"INSERT INTO pipeline_drafts VALUES ({marks})", astuple(draft))

    def get(self, project_id: str, draft_id: str) -> Draft | None:
        with self._lock:
            row = self._db.execute(
                "SELECT * FROM pipeline_drafts WHERE project_id = ? AND id = ?",
                (project_id, draft_id),
            ).fetchone()
        return Draft(*row) if row else None

    def list(self, project_id: str) -> list[Draft]:
        with self._lock:
            rows = self._db.execute(
                "SELECT * FROM pipeline_drafts WHERE project_id = ? ORDER BY created_at DESC, id",
                (project_id,),
            ).fetchall()
        return [Draft(*r) for r in rows]

    def update(self, draft: Draft) -> None:
        sets = ", ".join(f"{c} = ?" for c in _COLS[2:])
        with self._lock:
            self._db.execute(
                f"UPDATE pipeline_drafts SET {sets} WHERE project_id = ? AND id = ?",
                (*astuple(draft)[2:], draft.project_id, draft.id),
            )
