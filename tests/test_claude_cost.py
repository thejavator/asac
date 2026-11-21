"""Real cost from ``claude -p --output-format json``: parsed, never invented."""

from __future__ import annotations

import json

import pytest

from asac.adapters.claude_code import parse_claude_report

REPORT = {
    "type": "result",
    "subtype": "success",
    "is_error": False,
    "num_turns": 2,
    "result": "done",
    "total_cost_usd": 0.1234,
    "usage": {
        "input_tokens": 100,
        "output_tokens": 50,
        "cache_read_input_tokens": 900,
        "cache_creation_input_tokens": 300,
    },
}


def test_reads_cost_and_tokens_from_the_json_report() -> None:
    r = parse_claude_report(json.dumps(REPORT))
    assert r.cost_usd == pytest.approx(0.1234)
    assert r.tokens == 100 + 50 + 900 + 300
    assert r.is_error is False and r.result == "done"


def test_skips_warning_lines_printed_before_the_json_object() -> None:
    raw = '[claude-code:unrecognized_model] {"model":"x"}\n' + json.dumps(REPORT)
    assert parse_claude_report(raw).cost_usd == pytest.approx(0.1234)


def test_missing_cost_is_unknown_not_zero() -> None:
    """A report without a cost must not be booked as a free step."""
    no_cost = {k: v for k, v in REPORT.items() if k != "total_cost_usd"}
    r = parse_claude_report(json.dumps(no_cost))
    assert r.cost_usd is None


def test_unparseable_output_is_an_error_not_a_zero_cost() -> None:
    with pytest.raises(ValueError, match="no JSON"):
        parse_claude_report("garbage with no object")


def test_error_report_is_flagged() -> None:
    r = parse_claude_report(json.dumps({**REPORT, "is_error": True, "subtype": "error_max_turns"}))
    assert r.is_error is True


def test_autorun_reports_the_real_cost_to_the_engine(
    tmp_path: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End to end through the adapter: the cost of the run reaches the spend, not 0."""
    from pathlib import Path

    from asac.adapters import AdapterContext
    from asac.adapters.claude_code import ClaudeCodeHarness
    from asac.loader.load import load_manifest

    project = Path(__file__).resolve().parent.parent / "examples" / "payments-service"
    work = tmp_path / "work"
    work.mkdir()
    bindir = tmp_path / "bin"
    bindir.mkdir()
    fake = bindir / "claude"
    fake.write_text("#!/bin/sh\necho 'warning line'\necho '" + json.dumps(REPORT) + "'\n")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bindir}:/usr/bin:/bin")
    h = ClaudeCodeHarness(
        AdapterContext(project, load_manifest(project / "asac.yaml"), tmp_path / "state",
                       autorun=True, work=work)
    )  # fmt: skip
    h.permissions("assist")
    r = h.run({"step": "requirements", "capability": "c", "agent": "ba", "skill": "spec"},
              {"run_id": "r1"})  # fmt: skip
    assert r["autorun"]["tool"] == "claude"
    assert r["cost_usd"] == pytest.approx(0.1234)
    assert r["tokens"] == 1350


def test_unknown_cost_blocks_a_run_that_has_a_cost_budget() -> None:
    """A cost budget is a promise: a step whose cost is unknown cannot keep it."""
    from asac.engine.governance import BLOCK, Spend, check_budget
    from asac.model.manifest import Budgets, PerRun

    class M:
        budgets = Budgets(per_run=PerRun(cost_usd=5))

    assert check_budget(M(), Spend(cost_usd=1.0, cost_unknown=True)).action == BLOCK  # type: ignore[arg-type]


def test_unknown_cost_is_fine_without_a_cost_budget() -> None:
    from asac.engine.governance import ALLOW, Spend, check_budget
    from asac.model.manifest import Budgets, PerRun

    class M:
        budgets = Budgets(per_run=PerRun(tokens=10_000))

    assert check_budget(M(), Spend(tokens=10, cost_unknown=True)).action == ALLOW  # type: ignore[arg-type]


def test_an_unknown_cost_survives_a_resume_and_still_blocks(tmp_path: pytest.TempPathFactory) -> None:
    """The unknown cost is in the audit: a later resume must not forget it and pass the budget."""
    from types import SimpleNamespace

    from asac.adapters.state_sqlite import SqliteStateStore
    from asac.engine.apply import _spend_so_far
    from asac.engine.governance import BLOCK, check_budget
    from asac.model.manifest import Budgets, PerRun

    store = SqliteStateStore(tmp_path / "s.db")  # type: ignore[operator]
    store.create_run("rr", "feature", "2026-01-01T00:00:00Z")
    store.append_audit("rr", "cli", "spend.recorded", "2026-01-01T00:00:00Z",
                       detail="tokens=10 cost_usd=0.0000 cost=unknown")  # fmt: skip

    spend = _spend_so_far(SimpleNamespace(store=store), "rr")  # type: ignore[arg-type]
    assert spend.cost_unknown is True
    manifest = SimpleNamespace(budgets=Budgets(per_run=PerRun(cost_usd=5)))
    assert check_budget(manifest, spend).action == BLOCK  # type: ignore[arg-type]
