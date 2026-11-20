"""Conformance suite for the JobQueue port, run against every adapter."""

from pathlib import Path

import pytest

from asac.adapters.jobs_sqlite import SqliteJobQueue
from asac.ports.jobs import JobQueue


@pytest.fixture(params=["sqlite", "postgres"])
def queue(request: pytest.FixtureRequest, tmp_path: Path) -> JobQueue:
    if request.param == "postgres":
        from asac.adapters.jobs_postgres import PostgresJobQueue

        from .postgres_fixture import fresh_postgres_dsn

        return PostgresJobQueue(fresh_postgres_dsn())
    return SqliteJobQueue(tmp_path / "jobs.db")


T0, T1, T2 = "2026-01-01T00:00:00Z", "2026-01-01T00:01:00Z", "2026-01-01T00:02:00Z"


def test_claim_is_fifo_and_exclusive(queue: JobQueue) -> None:
    a = queue.enqueue("resume", "{}", T0)
    b = queue.enqueue("resume", "{}", T0)
    first = queue.claim(T0, T1)
    second = queue.claim(T0, T1)
    assert first and second and (first.job_id, second.job_id) == (a, b)
    assert queue.claim(T0, T1) is None


def test_future_job_is_not_due(queue: JobQueue) -> None:
    queue.enqueue("x", "{}", T0, run_after=T2)
    assert queue.claim(T1, T2) is None
    assert queue.claim(T2, "2026-01-01T00:03:00Z") is not None


def test_expired_lease_is_reclaimed(queue: JobQueue) -> None:
    queue.enqueue("x", "{}", T0)
    job = queue.claim(T0, T1)
    assert job and job.attempts == 1
    again = queue.claim(T2, "2026-01-01T00:03:00Z")
    assert again and again.job_id == job.job_id and again.attempts == 2


def test_complete_and_fail(queue: JobQueue) -> None:
    a = queue.enqueue("x", "{}", T0)
    queue.claim(T0, T1)
    queue.complete(a)
    assert queue.get(a).status == "done"
    b = queue.enqueue("x", "{}", T0)
    queue.claim(T0, T1)
    queue.fail(b, "boom", retry_at=T1)
    assert queue.get(b).status == "queued" and queue.get(b).error == "boom"
    queue.claim(T1, T2)
    queue.fail(b, "boom", retry_at=None)
    assert queue.get(b).status == "failed"


def test_retries_stop_at_max_attempts(queue: JobQueue) -> None:
    j = queue.enqueue("x", "{}", T0)
    queue.claim(T0, T1)
    queue.fail(j, "e", retry_at=T0, max_attempts=1)
    assert queue.get(j).status == "failed"


def test_postgres_workers_never_share_a_job() -> None:
    """Several workers on their own connections claim at once: SKIP LOCKED keeps them apart."""
    from concurrent.futures import ThreadPoolExecutor

    from asac.adapters.jobs_postgres import PostgresJobQueue

    from .postgres_fixture import fresh_postgres_dsn

    dsn = fresh_postgres_dsn()
    seed = PostgresJobQueue(dsn)
    ids = {seed.enqueue("x", "{}", T0) for _ in range(40)}

    def work() -> list[int]:
        q, got = PostgresJobQueue(dsn), []
        while (job := q.claim(T0, T1)) is not None:
            got.append(job.job_id)
        q.close()
        return got

    with ThreadPoolExecutor(4) as pool:
        claimed = [j for part in pool.map(lambda _: work(), range(4)) for j in part]
    assert sorted(claimed) == sorted(ids)
