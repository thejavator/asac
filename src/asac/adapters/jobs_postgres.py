"""PostgreSQL adapter for the ``JobQueue`` port. ``claim`` uses ``FOR UPDATE SKIP LOCKED``,
so several workers never take the same job and never wait on each other."""

from __future__ import annotations

import psycopg

from asac.ports.jobs import Job, JobStatus
from asac.ports.state import NotFound

SCHEMA = [
    """CREATE TABLE IF NOT EXISTS jobs (
        job_id BIGSERIAL PRIMARY KEY, kind TEXT NOT NULL, payload TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'queued', attempts INTEGER NOT NULL DEFAULT 0,
        run_after TEXT NOT NULL, lease_until TEXT, error TEXT, created_at TEXT NOT NULL)""",
    "CREATE INDEX IF NOT EXISTS jobs_due ON jobs (status, run_after)",
]
_COLS = "job_id, kind, payload, status, attempts, run_after, error"


class PostgresJobQueue:
    def __init__(self, dsn: str) -> None:
        self._db = psycopg.connect(dsn, autocommit=True)
        for stmt in SCHEMA:
            self._db.execute(stmt)

    def close(self) -> None:
        self._db.close()

    def enqueue(self, kind: str, payload: str, at: str, run_after: str | None = None) -> int:
        row = self._db.execute(
            "INSERT INTO jobs (kind, payload, run_after, created_at) "
            "VALUES (%s, %s, %s, %s) RETURNING job_id",
            (kind, payload, run_after or at, at),
        ).fetchone()
        assert row is not None
        return int(row[0])

    def claim(self, now: str, lease_until: str, kind: str | None = None) -> Job | None:
        row = self._db.execute(
            "UPDATE jobs SET status='running', attempts=attempts+1, lease_until=%s "
            "WHERE job_id = (SELECT job_id FROM jobs WHERE run_after <= %s AND "
            "(status='queued' OR (status='running' AND lease_until <= %s)) "
            "AND (%s::text IS NULL OR kind = %s) "
            "ORDER BY run_after, job_id LIMIT 1 FOR UPDATE SKIP LOCKED) "
            f"RETURNING {_COLS}",
            (lease_until, now, now, kind, kind),
        ).fetchone()
        return _job(row) if row else None

    def complete(self, job_id: int) -> None:
        self._db.execute(
            "UPDATE jobs SET status='done', lease_until=NULL WHERE job_id=%s", (job_id,)
        )

    def fail(self, job_id: int, error: str, retry_at: str | None, max_attempts: int = 5) -> None:
        job = self.get(job_id)
        if retry_at and job.attempts < max_attempts:
            self._db.execute(
                "UPDATE jobs SET status='queued', run_after=%s, error=%s, lease_until=NULL "
                "WHERE job_id=%s",
                (retry_at, error[:500], job_id),
            )
        else:
            self._db.execute(
                "UPDATE jobs SET status='failed', error=%s, lease_until=NULL WHERE job_id=%s",
                (error[:500], job_id),
            )

    def get(self, job_id: int) -> Job:
        row = self._db.execute(
            f"SELECT {_COLS} FROM jobs WHERE job_id=%s",
            (job_id,),
        ).fetchone()
        if row is None:
            raise NotFound(f"unknown job {job_id}")
        return _job(row)


def _job(row: tuple) -> Job:  # type: ignore[type-arg]
    status: JobStatus = row[3]
    return Job(int(row[0]), row[1], row[2], status, row[4], row[5], row[6])
