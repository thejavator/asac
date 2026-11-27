"""The organisation overview: summed across projects from each audit, labelled declared."""

from __future__ import annotations

from pathlib import Path

import pytest

from asac.engine.runtime import open_store
from asac.portal.overview import figures_for, unavailable
from asac.ports.state import AuditRecord, RunRecord
from tests.test_api import client_for, env, org, start_run  # noqa: F401  (env, org: fixtures)


def _a(seq: int, action: str, detail: str = "", step: str | None = "s") -> AuditRecord:
    return AuditRecord(seq, "2026-01-01T00:00:00Z", "r1", step, "cli", action, detail)


def _r(run_id: str, status: str) -> RunRecord:
    return RunRecord(run_id, "feature", status, "2026-01-01T00:00:00Z")


# -- the summing rules, on plain lists ----------------------------------------------------------


def test_spend_is_read_from_the_audit_the_way_the_engine_reads_it() -> None:
    entries = [
        _a(1, "spend.recorded", "tokens=1000 cost_usd=0.1200"),
        _a(2, "spend.recorded", "tokens=500 cost_usd=0.0300"),
        _a(3, "spend.recorded", "not a spend line"),  # ignored, as in RunState
    ]
    f = figures_for("p", "P", None, [_r("r1", "completed")], [("r1", entries)], 0)
    assert f.tokens == 1500 and f.cost_usd == pytest.approx(0.15)
    assert f.cost_unknown_runs == 0


def test_a_run_with_unknown_cost_is_counted() -> None:
    entries = [_a(1, "spend.recorded", "tokens=0 cost_usd=0.0000 cost=unknown")]
    f = figures_for("p", "P", None, [_r("r1", "completed")], [("r1", entries)], 0)
    assert f.cost_unknown_runs == 1


def test_run_statuses_are_grouped() -> None:
    runs = [_r("a", "running"), _r("b", "gate_waiting"), _r("c", "completed"),
            _r("d", "blocked"), _r("e", "failed"), _r("f", "killed")]  # fmt: skip
    f = figures_for("p", "P", None, runs, [], 2)
    assert (f.runs, f.active, f.completed, f.problems, f.pending_gates) == (6, 2, 1, 3, 2)


def test_security_events_and_checks_are_counted() -> None:
    entries = [
        _a(1, "integrity.violated", "asac.yaml"),
        _a(2, "sandbox.denied", "read /home/x/.ssh/id_rsa"),
        _a(3, "sandbox.denied", "net evil.example"),
        _a(4, "hook.passed", "post_step tests-green"),
        _a(5, "hook.failed", "post_step spec-present"),
        _a(6, "hook.passed", "pre_tool no-secrets"),
    ]
    f = figures_for("p", "P", None, [_r("r1", "blocked")], [("r1", entries)], 0)
    assert (f.integrity_violations, f.sandbox_denials) == (1, 2)
    assert (f.hooks_passed, f.hooks_failed) == (2, 1)
    assert f.check_pass_rate == pytest.approx(2 / 3)


def test_no_hook_means_no_pass_rate_rather_than_zero() -> None:
    assert figures_for("p", "P", None, [], [], 0).check_pass_rate is None


def test_an_unreadable_project_is_marked_not_dropped() -> None:
    f = unavailable("p", "P", "team")
    assert f.unavailable and f.runs == 0


# -- the endpoint -------------------------------------------------------------------------------


def test_overview_is_labelled_declared(org: Path) -> None:  # noqa: F811
    body = client_for(org, "carol").get("/api/v1/overview").json()
    assert body["assurance"] == "declared"


def test_overview_lists_only_the_projects_a_person_can_see(org: Path) -> None:  # noqa: F811
    alice = client_for(org, "alice").get("/api/v1/overview").json()
    assert [p["project_id"] for p in alice["projects"]] == ["payments"]
    carol = client_for(org, "carol").get("/api/v1/overview").json()  # auditor sees all
    assert sorted(p["project_id"] for p in carol["projects"]) == ["billing", "payments"]
    dave = client_for(org, "dave").get("/api/v1/overview").json()
    assert [p["project_id"] for p in dave["projects"]] == ["billing"]


def test_overview_counts_a_real_run(org: Path) -> None:  # noqa: F811
    manifest = org.parent / "payments/asac.yaml"
    start_run(manifest, "payments")
    body = client_for(org, "carol").get("/api/v1/overview").json()
    pay = next(p for p in body["projects"] if p["project_id"] == "payments")
    with open_store(manifest, "payments") as store:
        runs = store.list_runs()
        pending = len(store.list_gates("pending"))
    assert pay["runs"] == len(runs) == 1
    assert pay["pending_gates"] == pending
    assert pay["tokens"] > 0  # the fake harness books tokens
    assert body["totals"]["runs"] == 1


def test_overview_needs_a_session(org: Path) -> None:  # noqa: F811
    r = client_for(org).get("/api/v1/overview")
    assert r.status_code == 401
    assert r.headers["content-type"].startswith("application/problem+json")
