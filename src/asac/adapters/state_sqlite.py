"""SQLite adapter for the ``StateStore`` port (local default, WAL mode)."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from asac.ports.state import (
    AuditRecord,
    EvidenceExists,
    EvidenceRecord,
    GateError,
    GateRecord,
    GateStatus,
    NotFound,
    RunExists,
    RunRecord,
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY, pipeline TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS steps (
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    step_id TEXT NOT NULL,
    status TEXT NOT NULL,
    PRIMARY KEY (run_id, step_id)
);
CREATE TABLE IF NOT EXISTS evidence (
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    evidence_id TEXT NOT NULL,
    produced_by TEXT NOT NULL,
    approved_by TEXT,
    bootstrapped INTEGER NOT NULL DEFAULT 0,
    at TEXT NOT NULL,
    PRIMARY KEY (run_id, evidence_id)
);
CREATE TABLE IF NOT EXISTS gates (
    gate_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    step_id TEXT NOT NULL,
    type TEXT NOT NULL,
    role TEXT,
    status TEXT NOT NULL,
    requested_at TEXT NOT NULL,
    timeout_at TEXT,
    decided_by TEXT,
    decided_at TEXT,
    comment TEXT,
    evidence_ids TEXT NOT NULL DEFAULT '[]',
    subject TEXT
);
CREATE TABLE IF NOT EXISTS audit (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    at TEXT NOT NULL,
    run_id TEXT,
    step_id TEXT,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    detail TEXT NOT NULL DEFAULT ''
);
CREATE TRIGGER IF NOT EXISTS evidence_no_update BEFORE UPDATE ON evidence
BEGIN SELECT RAISE(ABORT, 'evidence is append-only'); END;
CREATE TRIGGER IF NOT EXISTS evidence_no_delete BEFORE DELETE ON evidence
BEGIN SELECT RAISE(ABORT, 'evidence is append-only'); END;
CREATE TRIGGER IF NOT EXISTS audit_no_update BEFORE UPDATE ON audit
BEGIN SELECT RAISE(ABORT, 'audit is append-only'); END;
CREATE TRIGGER IF NOT EXISTS audit_no_delete BEFORE DELETE ON audit
BEGIN SELECT RAISE(ABORT, 'audit is append-only'); END;
"""


def _gate(row: sqlite3.Row) -> GateRecord:
    return GateRecord(
        gate_id=row["gate_id"],
        run_id=row["run_id"],
        step_id=row["step_id"],
        type=row["type"],
        role=row["role"],
        status=row["status"],
        requested_at=row["requested_at"],
        timeout_at=row["timeout_at"],
        decided_by=row["decided_by"],
        decided_at=row["decided_at"],
        comment=row["comment"],
        evidence_ids=tuple(json.loads(row["evidence_ids"])),
        subject=row["subject"],
    )


class SqliteStateStore:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._conn = sqlite3.connect(path, check_same_thread=False)  # LockedStore serialises
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.execute("PRAGMA journal_mode = WAL")
        self._conn.executescript(SCHEMA)
        self._migrate()

    def _migrate(self) -> None:
        """Add columns that newer versions need to databases created by older ones."""
        cols = {r["name"] for r in self._conn.execute("PRAGMA table_info(gates)")}
        if "subject" not in cols:
            with self._conn:
                self._conn.execute("ALTER TABLE gates ADD COLUMN subject TEXT")

    def close(self) -> None:
        self._conn.close()

    # runs and steps -------------------------------------------------------
    def create_run(self, run_id: str, pipeline: str, at: str) -> None:
        try:
            with self._conn:
                self._conn.execute(
                    "INSERT INTO runs VALUES (?, ?, 'running', ?)", (run_id, pipeline, at)
                )
        except sqlite3.IntegrityError as exc:
            raise RunExists(run_id) from exc

    def get_run(self, run_id: str) -> RunRecord:
        row = self._conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        if row is None:
            raise NotFound(f"run '{run_id}' not found")
        return RunRecord(row["run_id"], row["pipeline"], row["status"], row["created_at"])

    def list_runs(self) -> list[RunRecord]:
        rows = self._conn.execute("SELECT * FROM runs ORDER BY rowid").fetchall()
        return [RunRecord(r["run_id"], r["pipeline"], r["status"], r["created_at"]) for r in rows]

    def set_run_status(self, run_id: str, status: str) -> None:
        with self._conn:
            cur = self._conn.execute(
                "UPDATE runs SET status = ? WHERE run_id = ?", (status, run_id)
            )
        if cur.rowcount == 0:
            raise NotFound(f"run '{run_id}' not found")

    def set_step_status(self, run_id: str, step_id: str, status: str) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT INTO steps (run_id, step_id, status) VALUES (?, ?, ?) "
                "ON CONFLICT (run_id, step_id) DO UPDATE SET status = excluded.status",
                (run_id, step_id, status),
            )

    def get_step_status(self, run_id: str, step_id: str) -> str | None:
        row = self._conn.execute(
            "SELECT status FROM steps WHERE run_id = ? AND step_id = ?", (run_id, step_id)
        ).fetchone()
        return None if row is None else str(row["status"])

    def list_steps(self, run_id: str) -> dict[str, str]:
        rows = self._conn.execute(
            "SELECT step_id, status FROM steps WHERE run_id = ? ORDER BY rowid", (run_id,)
        ).fetchall()
        return {r["step_id"]: r["status"] for r in rows}

    # evidence -------------------------------------------------------------
    def add_evidence(
        self,
        run_id: str,
        evidence_id: str,
        produced_by: str,
        at: str,
        approved_by: str | None = None,
        bootstrapped: bool = False,
    ) -> None:
        self.get_run(run_id)
        try:
            with self._conn:
                self._conn.execute(
                    "INSERT INTO evidence VALUES (?, ?, ?, ?, ?, ?)",
                    (run_id, evidence_id, produced_by, approved_by, int(bootstrapped), at),
                )
        except sqlite3.IntegrityError as exc:
            raise EvidenceExists(f"{evidence_id} already recorded for {run_id}") from exc

    def has_evidence(self, run_id: str, evidence_id: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM evidence WHERE run_id = ? AND evidence_id = ?", (run_id, evidence_id)
        ).fetchone()
        return row is not None

    def list_evidence(self, run_id: str) -> list[EvidenceRecord]:
        rows = self._conn.execute(
            "SELECT * FROM evidence WHERE run_id = ? ORDER BY rowid", (run_id,)
        ).fetchall()
        return [
            EvidenceRecord(
                r["run_id"],
                r["evidence_id"],
                r["produced_by"],
                r["approved_by"],
                bool(r["bootstrapped"]),
                r["at"],
            )
            for r in rows
        ]

    # gates ----------------------------------------------------------------
    def open_gate(self, gate: GateRecord) -> None:
        try:
            with self._conn:
                self._conn.execute(
                    "INSERT INTO gates (gate_id, run_id, step_id, type, role, status, "
                    "requested_at, timeout_at, evidence_ids, subject) "
                    "VALUES (?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?)",
                    (
                        gate.gate_id,
                        gate.run_id,
                        gate.step_id,
                        gate.type,
                        gate.role,
                        gate.requested_at,
                        gate.timeout_at,
                        json.dumps(list(gate.evidence_ids)),
                        gate.subject,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise GateError(f"gate '{gate.gate_id}' already exists") from exc

    def decide_gate(
        self, gate_id: str, status: GateStatus, decided_by: str, at: str, comment: str | None
    ) -> GateRecord:
        if status not in ("approved", "rejected", "expired"):
            raise GateError(f"invalid decision '{status}'")
        with self._conn:
            row = self._conn.execute(
                "SELECT status FROM gates WHERE gate_id = ?", (gate_id,)
            ).fetchone()
            if row is None:
                raise NotFound(f"gate '{gate_id}' not found")
            if row["status"] != "pending":
                raise GateError(f"gate '{gate_id}' is already {row['status']}")
            self._conn.execute(
                "UPDATE gates SET status = ?, decided_by = ?, decided_at = ?, comment = ? "
                "WHERE gate_id = ?",
                (status, decided_by, at, comment, gate_id),
            )
        return self.get_gate(gate_id)

    def reopen_gate(self, gate_id: str) -> GateRecord:
        with self._conn:
            row = self._conn.execute(
                "SELECT status FROM gates WHERE gate_id = ?", (gate_id,)
            ).fetchone()
            if row is None:
                raise NotFound(f"gate '{gate_id}' not found")
            if row["status"] != "rejected":
                raise GateError(f"only a rejected gate can be reopened (is {row['status']})")
            self._conn.execute(
                "UPDATE gates SET status = 'pending', decided_by = NULL, decided_at = NULL, "
                "comment = NULL WHERE gate_id = ?",
                (gate_id,),
            )
        return self.get_gate(gate_id)

    def get_gate(self, gate_id: str) -> GateRecord:
        row = self._conn.execute("SELECT * FROM gates WHERE gate_id = ?", (gate_id,)).fetchone()
        if row is None:
            raise NotFound(f"gate '{gate_id}' not found")
        return _gate(row)

    def list_gates(self, status: GateStatus | None = None) -> list[GateRecord]:
        if status is None:
            rows = self._conn.execute("SELECT * FROM gates ORDER BY rowid").fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM gates WHERE status = ? ORDER BY rowid", (status,)
            ).fetchall()
        return [_gate(r) for r in rows]

    # audit ----------------------------------------------------------------
    def append_audit(
        self,
        run_id: str | None,
        actor: str,
        action: str,
        at: str,
        step_id: str | None = None,
        detail: str = "",
    ) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT INTO audit (at, run_id, step_id, actor, action, detail) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (at, run_id, step_id, actor, action, detail),
            )

    def audit(self, run_id: str | None = None) -> list[AuditRecord]:
        sql = "SELECT * FROM audit"
        args: tuple[Any, ...] = ()
        if run_id is not None:
            sql += " WHERE run_id = ?"
            args = (run_id,)
        rows = self._conn.execute(sql + " ORDER BY seq", args).fetchall()
        return [
            AuditRecord(
                r["seq"], r["at"], r["run_id"], r["step_id"], r["actor"], r["action"], r["detail"]
            )
            for r in rows
        ]
