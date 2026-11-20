"""PostgreSQL adapter for the ``StateStore`` port (team deployments).

Same contract as the SQLite adapter, enforced by the same conformance suite. Evidence and
audit are append-only through triggers, so even a direct SQL client cannot rewrite them.
"""

from __future__ import annotations

import json
import re
from typing import Any

import psycopg
from psycopg import errors
from psycopg.rows import dict_row

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

SCHEMA = [
    """CREATE TABLE IF NOT EXISTS runs (
        n BIGSERIAL, run_id TEXT PRIMARY KEY, pipeline TEXT NOT NULL,
        status TEXT NOT NULL, created_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS steps (
        n BIGSERIAL, run_id TEXT NOT NULL REFERENCES runs(run_id), step_id TEXT NOT NULL,
        status TEXT NOT NULL, PRIMARY KEY (run_id, step_id))""",
    """CREATE TABLE IF NOT EXISTS evidence (
        n BIGSERIAL, run_id TEXT NOT NULL REFERENCES runs(run_id), evidence_id TEXT NOT NULL,
        produced_by TEXT NOT NULL, approved_by TEXT, bootstrapped BOOLEAN NOT NULL DEFAULT FALSE,
        at TEXT NOT NULL, PRIMARY KEY (run_id, evidence_id))""",
    """CREATE TABLE IF NOT EXISTS gates (
        n BIGSERIAL, gate_id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(run_id),
        step_id TEXT NOT NULL, type TEXT NOT NULL, role TEXT, status TEXT NOT NULL,
        requested_at TEXT NOT NULL, timeout_at TEXT, decided_by TEXT, decided_at TEXT,
        comment TEXT, evidence_ids TEXT NOT NULL DEFAULT '[]')""",
    """CREATE TABLE IF NOT EXISTS audit (
        seq BIGSERIAL PRIMARY KEY, at TEXT NOT NULL, run_id TEXT, step_id TEXT,
        actor TEXT NOT NULL, action TEXT NOT NULL, detail TEXT NOT NULL DEFAULT '')""",
    """CREATE OR REPLACE FUNCTION asac_append_only() RETURNS trigger AS $$
       BEGIN RAISE EXCEPTION '% is append-only', TG_TABLE_NAME; END; $$ LANGUAGE plpgsql""",
    "DROP TRIGGER IF EXISTS evidence_append_only ON evidence",
    """CREATE TRIGGER evidence_append_only BEFORE UPDATE OR DELETE ON evidence
       FOR EACH ROW EXECUTE FUNCTION asac_append_only()""",
    "DROP TRIGGER IF EXISTS audit_append_only ON audit",
    """CREATE TRIGGER audit_append_only BEFORE UPDATE OR DELETE ON audit
       FOR EACH ROW EXECUTE FUNCTION asac_append_only()""",
]


def _gate(row: dict[str, Any]) -> GateRecord:
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
    )


def _run(r: dict[str, Any]) -> RunRecord:
    return RunRecord(r["run_id"], r["pipeline"], r["status"], r["created_at"])


class PostgresStateStore:
    def __init__(self, dsn: str, schema: str | None = None) -> None:
        self._conn: psycopg.Connection[dict[str, Any]] = psycopg.connect(
            dsn, autocommit=True, row_factory=dict_row
        )
        if schema is not None:  # one project = one schema: same tables, separate data
            if not re.fullmatch(r"[a-z][a-z0-9_]{0,60}", schema):
                raise ValueError("invalid schema name")
            self._conn.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')  # noqa: S608
            self._conn.execute(f'SET search_path TO "{schema}"')
        with self._conn.transaction():
            # One initialiser at a time: two processes starting together must not race.
            self._conn.execute("SELECT pg_advisory_xact_lock(727340)")
            for statement in SCHEMA:
                self._conn.execute(statement)

    def close(self) -> None:
        self._conn.close()

    def _one(self, sql: str, args: tuple[Any, ...]) -> dict[str, Any] | None:
        return self._conn.execute(sql, args).fetchone()

    def _all(self, sql: str, args: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        return self._conn.execute(sql, args).fetchall()

    # runs and steps -------------------------------------------------------
    def create_run(self, run_id: str, pipeline: str, at: str) -> None:
        try:
            self._conn.execute(
                "INSERT INTO runs (run_id, pipeline, status, created_at) "
                "VALUES (%s, %s, 'running', %s)",
                (run_id, pipeline, at),
            )
        except errors.UniqueViolation as exc:
            raise RunExists(run_id) from exc

    def get_run(self, run_id: str) -> RunRecord:
        row = self._one("SELECT * FROM runs WHERE run_id = %s", (run_id,))
        if row is None:
            raise NotFound(f"run '{run_id}' not found")
        return _run(row)

    def list_runs(self) -> list[RunRecord]:
        return [_run(r) for r in self._all("SELECT * FROM runs ORDER BY n")]

    def set_run_status(self, run_id: str, status: str) -> None:
        cur = self._conn.execute("UPDATE runs SET status = %s WHERE run_id = %s", (status, run_id))
        if cur.rowcount == 0:
            raise NotFound(f"run '{run_id}' not found")

    def set_step_status(self, run_id: str, step_id: str, status: str) -> None:
        self._conn.execute(
            "INSERT INTO steps (run_id, step_id, status) VALUES (%s, %s, %s) "
            "ON CONFLICT (run_id, step_id) DO UPDATE SET status = EXCLUDED.status",
            (run_id, step_id, status),
        )

    def get_step_status(self, run_id: str, step_id: str) -> str | None:
        row = self._one(
            "SELECT status FROM steps WHERE run_id = %s AND step_id = %s", (run_id, step_id)
        )
        return None if row is None else str(row["status"])

    def list_steps(self, run_id: str) -> dict[str, str]:
        rows = self._all(
            "SELECT step_id, status FROM steps WHERE run_id = %s ORDER BY n", (run_id,)
        )
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
            self._conn.execute(
                "INSERT INTO evidence (run_id, evidence_id, produced_by, approved_by, "
                "bootstrapped, at) VALUES (%s, %s, %s, %s, %s, %s)",
                (run_id, evidence_id, produced_by, approved_by, bootstrapped, at),
            )
        except errors.UniqueViolation as exc:
            raise EvidenceExists(f"{evidence_id} already recorded for {run_id}") from exc

    def has_evidence(self, run_id: str, evidence_id: str) -> bool:
        row = self._one(
            "SELECT 1 AS x FROM evidence WHERE run_id = %s AND evidence_id = %s",
            (run_id, evidence_id),
        )
        return row is not None

    def list_evidence(self, run_id: str) -> list[EvidenceRecord]:
        rows = self._all("SELECT * FROM evidence WHERE run_id = %s ORDER BY n", (run_id,))
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
            self._conn.execute(
                "INSERT INTO gates (gate_id, run_id, step_id, type, role, status, "
                "requested_at, timeout_at, evidence_ids) "
                "VALUES (%s, %s, %s, %s, %s, 'pending', %s, %s, %s)",
                (
                    gate.gate_id,
                    gate.run_id,
                    gate.step_id,
                    gate.type,
                    gate.role,
                    gate.requested_at,
                    gate.timeout_at,
                    json.dumps(list(gate.evidence_ids)),
                ),
            )
        except errors.UniqueViolation as exc:
            raise GateError(f"gate '{gate.gate_id}' already exists") from exc

    def _locked_status(self, gate_id: str) -> str:
        """Row lock inside the caller's transaction: two deciders cannot both win."""
        row = self._one("SELECT status FROM gates WHERE gate_id = %s FOR UPDATE", (gate_id,))
        if row is None:
            raise NotFound(f"gate '{gate_id}' not found")
        return str(row["status"])

    def decide_gate(
        self, gate_id: str, status: GateStatus, decided_by: str, at: str, comment: str | None
    ) -> GateRecord:
        if status not in ("approved", "rejected", "expired"):
            raise GateError(f"invalid decision '{status}'")
        with self._conn.transaction():
            current = self._locked_status(gate_id)
            if current != "pending":
                raise GateError(f"gate '{gate_id}' is already {current}")
            self._conn.execute(
                "UPDATE gates SET status = %s, decided_by = %s, decided_at = %s, comment = %s "
                "WHERE gate_id = %s",
                (status, decided_by, at, comment, gate_id),
            )
        return self.get_gate(gate_id)

    def reopen_gate(self, gate_id: str) -> GateRecord:
        with self._conn.transaction():
            current = self._locked_status(gate_id)
            if current != "rejected":
                raise GateError(f"only a rejected gate can be reopened (is {current})")
            self._conn.execute(
                "UPDATE gates SET status = 'pending', decided_by = NULL, decided_at = NULL, "
                "comment = NULL WHERE gate_id = %s",
                (gate_id,),
            )
        return self.get_gate(gate_id)

    def get_gate(self, gate_id: str) -> GateRecord:
        row = self._one("SELECT * FROM gates WHERE gate_id = %s", (gate_id,))
        if row is None:
            raise NotFound(f"gate '{gate_id}' not found")
        return _gate(row)

    def list_gates(self, status: GateStatus | None = None) -> list[GateRecord]:
        if status is None:
            rows = self._all("SELECT * FROM gates ORDER BY n")
        else:
            rows = self._all("SELECT * FROM gates WHERE status = %s ORDER BY n", (status,))
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
        self._conn.execute(
            "INSERT INTO audit (at, run_id, step_id, actor, action, detail) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (at, run_id, step_id, actor, action, detail),
        )

    def audit(self, run_id: str | None = None) -> list[AuditRecord]:
        if run_id is None:
            rows = self._all("SELECT * FROM audit ORDER BY seq")
        else:
            rows = self._all("SELECT * FROM audit WHERE run_id = %s ORDER BY seq", (run_id,))
        return [
            AuditRecord(
                r["seq"], r["at"], r["run_id"], r["step_id"], r["actor"], r["action"], r["detail"]
            )
            for r in rows
        ]
