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


def test_claim_can_be_limited_to_one_kind_and_leaves_the_others_untouched(queue: JobQueue) -> None:
    """A worker that runs `run` jobs must not consume a `resume` or a webhook job."""
    other = queue.enqueue("resume", "{}", T0)
    mine = queue.enqueue("run", "{}", T0)
    got = queue.claim(T0, T1, kind="run")
    assert got and got.job_id == mine and got.kind == "run"
    assert queue.get(other).status == "queued" and queue.get(other).attempts == 0
    assert queue.claim(T0, T1, kind="run") is None  # nothing else of that kind
    assert queue.claim(T0, T1) is not None  # without a kind, the other one is still there


def test_claim_of_a_kind_still_respects_the_lease_and_the_due_time(queue: JobQueue) -> None:
    queue.enqueue("run", "{}", T0, run_after=T2)
    assert queue.claim(T1, T2, kind="run") is None  # not due
    job = queue.claim(T2, "2026-01-01T00:03:00Z", kind="run")
    assert job and job.attempts == 1
    assert queue.claim(T2, "2026-01-01T00:03:00Z", kind="run") is None  # leased
    again = queue.claim("2026-01-01T00:04:00Z", "2026-01-01T00:05:00Z", kind="run")
    assert again and again.attempts == 2  # the lease ran out: handed over again
