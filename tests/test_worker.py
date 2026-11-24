"""F62: `asac apply --enqueue` puts a run in the job queue; `asac worker` takes it and runs it.

Real queue (SQLite), real engine, real worktrees. Only the agent is a stand-in (`--harness fake`).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from asac.adapters.jobs_sqlite import SqliteJobQueue
from asac.cli import app
from asac.engine.runtime import store_for
from tests.conftest import init_git

runner = CliRunner()


@pytest.fixture
def project(sandbox_project: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("ASAC_FIXED_TIME", "2026-01-01T09:00:00Z")
    monkeypatch.setenv("ASAC_AUTORUN", "0")
    monkeypatch.setenv("ASAC_SANDBOX", "0")
    monkeypatch.setenv("ASAC_ISOLATE", "0")  # the fake harness needs no worktree
    init_git(sandbox_project)
    return sandbox_project


def asac(project: Path, *args: str):  # type: ignore[no-untyped-def]
    return runner.invoke(app, [*args, "-f", str(project / "asac.yaml")])


def _queue(project: Path) -> SqliteJobQueue:
    from asac.adapters import state_dir

    folder = state_dir(project)
    folder.mkdir(parents=True, exist_ok=True)
    return SqliteJobQueue(folder / "jobs.db")


def _jobs(project: Path) -> list[tuple[int, str, str, int, str | None]]:
    q = _queue(project)
    rows = q._db.execute("select job_id, kind, status, attempts, error from jobs order by job_id")
    return list(rows.fetchall())


def test_enqueue_puts_a_run_job_in_the_queue_and_returns_its_number(project: Path) -> None:
    """F62.1: pipeline, run id and harness are in the job; nothing runs yet."""
    r = asac(project, "apply", "-p", "feature", "--harness", "fake", "--run-id", "q1", "--enqueue")
    assert r.exit_code == 0, r.output
    assert "job 1" in r.output and "q1" in r.output
    (job,) = _jobs(project)
    assert job[:3] == (1, "run", "queued")
    payload = json.loads(_queue(project).get(1).payload)
    assert payload == {"pipeline": "feature", "run_id": "q1", "harness": "fake"}
    assert store_for(project / "asac.yaml").list_runs() == []  # the run does not exist yet


def test_enqueue_without_a_run_id_names_the_run_for_you(project: Path) -> None:
    asac(project, "apply", "-p", "feature", "--harness", "fake", "--enqueue")
    asac(project, "apply", "-p", "feature", "--harness", "fake", "--enqueue")
    ids = [json.loads(_queue(project).get(n).payload)["run_id"] for n in (1, 2)]
    assert len(set(ids)) == 2 and all(i for i in ids)  # two distinct names


def test_enqueue_refuses_an_unknown_pipeline_before_queueing(project: Path) -> None:
    r = asac(project, "apply", "-p", "nope", "--harness", "fake", "--enqueue")
    assert r.exit_code == 1 and "unknown pipeline" in r.output
    assert _jobs(project) == []


def test_the_worker_takes_the_job_creates_the_run_and_runs_it(project: Path) -> None:
    """F62.2 and F62.6: the run is created and executed, the job marked done, one line printed."""
    asac(project, "apply", "-p", "feature", "--harness", "fake", "--run-id", "w1", "--enqueue")
    r = asac(project, "worker", "--once")
    assert r.exit_code == 0, r.output
    assert [x for x in r.output.splitlines() if x.startswith("job 1")] == [
        "job 1  w1  waiting for gate gate_w1_requirements"
    ]
    assert _jobs(project)[0][2] == "done"
    runs = store_for(project / "asac.yaml").list_runs()
    assert [(x.run_id, x.status) for x in runs] == [("w1", "gate_waiting")]


def test_a_run_that_stops_at_a_gate_is_a_finished_job(project: Path) -> None:
    """A gate is a stable result: the person decides later. The job is done, not retried."""
    asac(project, "apply", "-p", "feature", "--harness", "fake", "--run-id", "w2", "--enqueue")
    asac(project, "worker", "--once")
    assert _jobs(project)[0][2:4] == ("done", 1)


def test_a_blocked_run_is_a_finished_job(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASAC_FAKE_RESULT", '{"tokens": 99999999}')  # over the token budget
    asac(project, "apply", "-p", "feature", "--harness", "fake", "--run-id", "w3", "--enqueue")
    r = asac(project, "worker", "--once")
    assert _jobs(project)[0][2] == "done" and "blocked" in r.output


def test_an_engine_error_fails_the_job_with_its_reason_and_queues_it_again(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """F62.3: an error result is retried, up to 5 attempts, and the reason is kept."""
    monkeypatch.setenv("ASAC_FAKE_FAIL", "requirements")
    asac(project, "apply", "-p", "feature", "--harness", "fake", "--run-id", "w4", "--enqueue")
    r = asac(project, "worker", "--once")
    assert "job 1  w4  failed" in r.output
    job = _jobs(project)[0]
    assert job[2] == "queued" and job[3] == 1 and "requirements" in (job[4] or "")


def test_a_job_that_keeps_failing_ends_failed_after_five_attempts(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ASAC_FAKE_FAIL", "requirements")
    asac(project, "apply", "-p", "feature", "--harness", "fake", "--run-id", "w5", "--enqueue")
    for n in range(7):
        monkeypatch.setenv("ASAC_FIXED_TIME", f"2026-01-01T09:{n + 1:02d}:00Z")
        asac(project, "worker", "--once")
    job = _jobs(project)[0]
    assert job[2] == "failed" and job[3] == 5, job  # never a sixth attempt
    assert "requirements" in (job[4] or "")


def test_an_expired_lease_gives_the_job_back_to_the_queue(project: Path) -> None:
    """F62.4: a worker that died with a job leaves it `running`; once the lease is over, another
    worker takes it."""
    asac(project, "apply", "-p", "feature", "--harness", "fake", "--run-id", "w6", "--enqueue")
    q = _queue(project)
    taken = q.claim("2026-01-01T09:00:00Z", "2026-01-01T09:05:00Z")  # the dead worker
    assert taken and taken.status == "running"
    assert asac(project, "worker", "--once").output.count("job ") == 0  # lease still running
    import os

    os.environ["ASAC_FIXED_TIME"] = "2026-01-01T09:10:00Z"
    r = asac(project, "worker", "--once")
    assert "job 1  w6" in r.output and _jobs(project)[0][2] == "done"


def _bounded(project: Path, seconds: int, *args: str):  # type: ignore[no-untyped-def]
    """Run the worker in a thread: a `--once` that never stops fails the test, it does not hang."""
    import threading

    box: list[object] = []
    t = threading.Thread(target=lambda: box.append(asac(project, *args)), daemon=True)
    t.start()
    t.join(seconds)
    assert box, f"`asac {' '.join(args)}` did not stop within {seconds}s"
    return box[0]


def test_once_handles_every_due_job_then_stops(project: Path) -> None:
    """F62.5."""
    for rid in ("a", "b", "c"):
        asac(project, "apply", "-p", "feature", "--harness", "fake", "--run-id", rid, "--enqueue")
    r = _bounded(project, 30, "worker", "--once")
    assert r.exit_code == 0 and sum(1 for x in r.output.splitlines() if x.startswith("job ")) == 3  # type: ignore[attr-defined]
    assert [j[2] for j in _jobs(project)] == ["done", "done", "done"]
    again = _bounded(project, 30, "worker", "--once")
    assert again.exit_code == 0 and "job " not in again.output  # type: ignore[attr-defined]


def test_jobs_are_taken_in_order_one_at_a_time(project: Path) -> None:
    for rid in ("first", "second"):
        asac(project, "apply", "-p", "feature", "--harness", "fake", "--run-id", rid, "--enqueue")
    out = asac(project, "worker", "--once").output
    assert out.index("job 1  first") < out.index("job 2  second")


def test_a_run_that_already_exists_is_resumed_not_recreated(project: Path) -> None:
    """At-least-once delivery: a job taken twice must not fail on `run exists`."""
    asac(project, "apply", "-p", "feature", "--harness", "fake", "--run-id", "w7", "--enqueue")
    asac(project, "worker", "--once")
    _queue(project)._db.execute("update jobs set status='queued', lease_until=NULL where job_id=1")
    r = asac(project, "worker", "--once")
    assert r.exit_code == 0 and _jobs(project)[0][2] == "done"
    assert len(store_for(project / "asac.yaml").list_runs()) == 1


def test_a_job_of_another_kind_is_left_alone(project: Path) -> None:
    """The queue also carries webhooks and resumes: the worker only takes `run` jobs."""
    q = _queue(project)
    q.enqueue("resume", "{}", "2026-01-01T09:00:00Z")
    r = asac(project, "worker", "--once")
    assert r.exit_code == 0 and "job " not in r.output
    assert _jobs(project)[0][2] == "queued"


def test_the_worker_uses_the_configured_runner_and_harness_like_apply(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """F62.7: the harness named in the job is the one that runs; the runner comes from the vars."""
    monkeypatch.setenv("ASAC_FAKE_DELEGATE", "1")
    monkeypatch.setenv("ASAC_RUNNER", "fake")
    asac(project, "apply", "-p", "feature", "--harness", "fake", "--run-id", "w8", "--enqueue")
    asac(project, "worker", "--once")
    audit = [a.action for a in store_for(project / "asac.yaml").audit("w8")]
    assert "run.created" in audit and "step.started" in audit


def test_worker_is_in_the_help_and_the_supported_list(project: Path) -> None:
    """F62.8."""
    assert "worker" in runner.invoke(app, ["--help"]).output
    from tests.test_help_scope import SUPPORTED

    assert "worker" in SUPPORTED


def test_the_state_of_a_run_taken_by_a_worker_matches_one_started_by_apply(project: Path) -> None:
    """The worker runs the same engine: same audit, same gate."""
    asac(project, "apply", "-p", "feature", "--harness", "fake", "--run-id", "direct")
    asac(project, "apply", "-p", "feature", "--harness", "fake", "--run-id", "queued", "--enqueue")
    asac(project, "worker", "--once")
    store = store_for(project / "asac.yaml")

    def shape(run: str) -> list[str]:
        return [a.action for a in store.audit(run)]

    assert shape("direct") == shape("queued")
