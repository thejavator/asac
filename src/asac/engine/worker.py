"""The worker: takes ``run`` jobs from the queue and runs them, one at a time.

A job is the request "run this pipeline": its payload names the pipeline, the run and the harness.
The worker creates the run (or finds it, when a job is delivered twice) and hands it to the engine,
as ``asac apply`` does. Delivery is at-least-once, so everything here is safe to repeat.

What counts as finished, and what is retried:

* the run is **done, waiting at a gate, or blocked** (exit 0, 2, 3): the engine gave a stable answer
  and a person acts next, so the job is complete. Running it again would change nothing.
* the engine **failed** (exit 1, or an error before it ran): the job goes back to the queue with the
  reason, up to ``MAX_ATTEMPTS`` times, then ends ``failed`` with that reason.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta

from asac import clock
from asac.engine.apply import Exit, Outcome
from asac.ports.jobs import Job, JobQueue

KIND = "run"
MAX_ATTEMPTS = 5
LEASE = timedelta(minutes=30)  # a worker that dies leaves its job; after this it is taken again
RETRY_AFTER = timedelta(seconds=30)


class BadJob(Exception):
    """A job whose payload cannot be run: retrying it cannot help."""


@dataclass(frozen=True)
class RunRequest:
    pipeline: str
    run_id: str
    harness: str | None = None

    def payload(self) -> str:
        return json.dumps(
            {"pipeline": self.pipeline, "run_id": self.run_id, "harness": self.harness}
            if self.harness
            else {"pipeline": self.pipeline, "run_id": self.run_id}
        )

    @staticmethod
    def parse(job: Job) -> RunRequest:
        try:
            data = json.loads(job.payload)
            return RunRequest(str(data["pipeline"]), str(data["run_id"]), data.get("harness"))
        except (ValueError, KeyError, TypeError) as exc:
            raise BadJob(f"job {job.job_id} has no usable payload ({exc})") from None


def enqueue_run(queue: JobQueue, request: RunRequest) -> int:
    return queue.enqueue(KIND, request.payload(), clock.now_iso())


@dataclass(frozen=True)
class Done:
    """What the worker did with one job, for the line it prints."""

    job_id: int
    run_id: str
    result: str
    finished: bool


# What the worker needs from the engine, passed in so this module knows nothing of the CLI.
Execute = Callable[[RunRequest], Outcome]


def work_once(queue: JobQueue, execute: Execute) -> Done | None:
    """Take the next due ``run`` job and run it. None when no job is due."""
    now = clock.now()
    job = queue.claim(clock.fmt(now), clock.fmt(now + LEASE), kind=KIND)
    if job is None:
        return None
    try:
        request = RunRequest.parse(job)
        outcome = execute(request)
    except BadJob as exc:
        queue.fail(job.job_id, str(exc), None)
        return Done(job.job_id, "", f"failed: {exc}", True)
    except Exception as exc:  # the engine or its set-up broke: retry, keep the reason
        return _retry(queue, job, "", str(exc) or type(exc).__name__)
    if outcome.code == Exit.ERROR:
        return _retry(queue, job, request.run_id, outcome.message)
    queue.complete(job.job_id)
    return Done(job.job_id, request.run_id, outcome.message, True)


def _retry(queue: JobQueue, job: Job, run_id: str, reason: str) -> Done:
    retry_at = clock.fmt(clock.now() + RETRY_AFTER)
    queue.fail(job.job_id, reason, retry_at, max_attempts=MAX_ATTEMPTS)
    return Done(job.job_id, run_id, f"failed: {reason}", False)
