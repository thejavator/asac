"""Port for the job queue (webhooks, resumes, runner work). At-least-once, one worker per job.

Adapters: SQLite (local), Postgres (``FOR UPDATE SKIP LOCKED``). Handlers must be idempotent:
a job whose lease expires is handed to another worker.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

JobStatus = Literal["queued", "running", "done", "failed"]


@dataclass(frozen=True)
class Job:
    job_id: int
    kind: str
    payload: str  # JSON text; the queue does not interpret it
    status: JobStatus
    attempts: int
    run_after: str
    error: str | None = None


class JobQueue(Protocol):
    def enqueue(self, kind: str, payload: str, at: str, run_after: str | None = None) -> int: ...
    def claim(self, now: str, lease_until: str) -> Job | None:
        """Take the oldest due job (queued, or running with an expired lease). None if empty."""
        ...

    def complete(self, job_id: int) -> None: ...
    def fail(self, job_id: int, error: str, retry_at: str | None, max_attempts: int = 5) -> None:
        """Requeue at ``retry_at`` while attempts remain, otherwise mark failed."""
        ...

    def get(self, job_id: int) -> Job: ...
