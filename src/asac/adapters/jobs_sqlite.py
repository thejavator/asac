"""SQLite adapter for the ``JobQueue`` port. ``claim`` is atomic (BEGIN IMMEDIATE)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from asac.ports.jobs import Job, JobStatus
from asac.ports.state import NotFound

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    job_id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    payload TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued',
    attempts INTEGER NOT NULL DEFAULT 0,
    run_after TEXT NOT NULL,
    lease_until TEXT,
    error TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS jobs_due ON jobs (status, run_after);
"""


class SqliteJobQueue:
    def __init__(self, path: Path | str) -> None:
        self._db = sqlite3.connect(str(path), timeout=10, isolation_level=None)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.executescript(SCHEMA)

    def close(self) -> None:
        self._db.close()

    def enqueue(self, kind: str, payload: str, at: str, run_after: str | None = None) -> int:
        cur = self._db.execute(
            "INSERT INTO jobs (kind, payload, run_after, created_at) VALUES (?, ?, ?, ?)",
            (kind, payload, run_after or at, at),
        )
        assert cur.lastrowid is not None
        return cur.lastrowid

    def claim(self, now: str, lease_until: str, kind: str | None = None) -> Job | None:
        self._db.execute("BEGIN IMMEDIATE")
        try:
            row = self._db.execute(
                "SELECT job_id FROM jobs WHERE run_after <= ? AND "
                "(status = 'queued' OR (status = 'running' AND lease_until <= ?)) "
                "AND (? IS NULL OR kind = ?) "
                "ORDER BY run_after, job_id LIMIT 1",
                (now, now, kind, kind),
            ).fetchone()
            if row is None:
                self._db.execute("COMMIT")
                return None
            self._db.execute(
                "UPDATE jobs SET status='running', attempts=attempts+1, lease_until=? "
                "WHERE job_id=?",
                (lease_until, row[0]),
            )
            self._db.execute("COMMIT")
        except Exception:
            self._db.execute("ROLLBACK")
            raise
        return self.get(row[0])

    def complete(self, job_id: int) -> None:
        self._db.execute(
            "UPDATE jobs SET status='done', lease_until=NULL WHERE job_id=?", (job_id,)
        )

    def fail(self, job_id: int, error: str, retry_at: str | None, max_attempts: int = 5) -> None:
        job = self.get(job_id)
        if retry_at and job.attempts < max_attempts:
            self._db.execute(
                "UPDATE jobs SET status='queued', run_after=?, error=?, lease_until=NULL "
                "WHERE job_id=?",
                (retry_at, error[:500], job_id),
            )
        else:
            self._db.execute(
                "UPDATE jobs SET status='failed', error=?, lease_until=NULL WHERE job_id=?",
                (error[:500], job_id),
            )

    def get(self, job_id: int) -> Job:
        row = self._db.execute(
            "SELECT job_id, kind, payload, status, attempts, run_after, error "
            "FROM jobs WHERE job_id=?",
            (job_id,),
        ).fetchone()
        if row is None:
            raise NotFound(f"unknown job {job_id}")
        status: JobStatus = row[3]
        return Job(row[0], row[1], row[2], status, row[4], row[5], row[6])
