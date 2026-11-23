"""The engine's seven readings of a run's audit, pinned on journals, BEFORE they move.

Each case is a list of audit entries (action, step, detail). The expected value is what the
engine's own functions answer today. The same journals are then asked of the new RunState: it
must answer the same, for every journal and every question. That is the proof the refactor
changed where the knowledge lives, and nothing it says.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from asac.engine import apply as engine
from asac.ports.state import AuditRecord

Row = tuple[str, str | None, str]


def _audit(rows: list[Row]) -> list[AuditRecord]:
    return [AuditRecord(i + 1, "t", "r", step, "cli", action, detail)
            for i, (action, step, detail) in enumerate(rows)]  # fmt: skip


def _ctx(rows: list[Row]) -> Any:
    store = SimpleNamespace(audit=lambda run_id=None: _audit(rows))
    return SimpleNamespace(store=store)


JOURNALS: dict[str, list[Row]] = {
    "empty": [],
    "plain handoff": [("step.handoff", "s", "brief")],
    "handoff then submit": [("step.handoff", "s", "b"), ("step.submitted", "s", "")],
    "submit, checks fail, handed back": [
        ("step.handoff", "s", "b"),
        ("step.submitted", "s", ""),
        ("step.handoff", "s", "returned: the checks failed"),
    ],  # fmt: skip
    "submit, back, submit again": [
        ("step.handoff", "s", "b"),
        ("step.submitted", "s", ""),
        ("step.handoff", "s", "returned"),
        ("step.submitted", "s", ""),
    ],  # fmt: skip
    "submit on another step only": [("step.handoff", "s", "b"), ("step.submitted", "t", "")],
    "tool launched": [("tool.launched", "s", "claude exit=0")],
    "tool launched on another step": [("tool.launched", "t", "claude exit=0")],
    "isolated run": [("run.created", None, "p"), ("workspace.created", None, "path=/x branch=b")],
    "isolation failed": [("workspace.failed", None, "no git")],
    "not isolated": [("run.created", None, "p"), ("step.started", "s", "a")],
    "iterations": [
        ("step.iteration", "s", "1 of 3 failed: x"),
        ("step.iteration", "s", "2 of 3 failed: x"),
        ("step.iteration", "t", "1 of 3 failed: y"),
    ],  # fmt: skip
    "spend": [
        ("spend.recorded", "s", "tokens=100 cost_usd=0.5000"),
        ("spend.recorded", "t", "tokens=50 cost_usd=0.2500"),
        ("spend.recorded", "s", "tokens=1 cost_usd=0.0100"),
    ],
    "spend with an unknown cost": [
        ("spend.recorded", "s", "tokens=10 cost_usd=0.0000 cost=unknown"),
        ("spend.recorded", "t", "tokens=5 cost_usd=0.1000"),
    ],
    "spend text that is not a spend": [("spend.recorded", "s", "free text")],
    "rejection then relaunch": [
        ("tool.launched", "s", "claude"),
        ("rejection.handled", "s", "1 of 2: r"),
        ("attempt.after_rejection", "s", "launch 1"),
        ("tool.launched", "s", "claude"),
    ],  # fmt: skip
    "rejection not yet answered": [
        ("tool.launched", "s", "claude"),
        ("rejection.handled", "s", "1 of 2: r"),
    ],  # fmt: skip
    "two rejections": [
        ("tool.launched", "s", "c"),
        ("rejection.handled", "s", "1"),
        ("attempt.after_rejection", "s", "launch 1"),
        ("rejection.handled", "s", "2"),
        ("attempt.after_rejection", "s", "launch 2"),
    ],  # fmt: skip
    "rejection on another step": [("rejection.handled", "t", "1")],
}

STEPS = ("s", "t", "absent")


def _engine_answers(rows: list[Row]) -> dict[str, Any]:
    ctx = _ctx(rows)
    out: dict[str, Any] = {"was_isolated": engine._was_isolated(ctx.store, "r")}
    sp = engine._spend_so_far(ctx, "r")
    out["spend"] = (sp.tokens, round(sp.cost_usd, 6), sp.cost_unknown)
    for s in STEPS:
        out[f"submitted:{s}"] = engine._submitted(ctx, "r", s)
        out[f"autorun_launched:{s}"] = engine._autorun_launched(ctx, "r", s)
        out[f"turns:{s}"] = engine._turns_so_far(ctx, "r", s)
        out[f"rejections:{s}"] = engine._rejections_so_far(ctx, "r", s)
        out[f"follows_a_rejection:{s}"] = engine._follows_a_rejection(ctx, "r", s)
    return out


@pytest.mark.parametrize("name", sorted(JOURNALS))
def test_the_engines_current_answers_are_stable(name: str) -> None:
    """Characterisation: runs against today's functions, and documents their answers."""
    assert _engine_answers(JOURNALS[name])  # computed without error for every journal


def test_pinned_answers_for_the_cases_that_matter() -> None:
    a = lambda n: _engine_answers(JOURNALS[n])  # noqa: E731
    assert a("handoff then submit")["submitted:s"] is True
    assert a("submit, checks fail, handed back")["submitted:s"] is False
    assert a("submit, back, submit again")["submitted:s"] is True
    assert a("submit on another step only")["submitted:s"] is False
    assert a("tool launched")["autorun_launched:s"] is True
    assert a("tool launched on another step")["autorun_launched:s"] is False
    assert a("isolated run")["was_isolated"] and a("isolation failed")["was_isolated"]
    assert not a("not isolated")["was_isolated"]
    assert a("iterations")["turns:s"] == 2 and a("iterations")["turns:t"] == 1
    assert a("spend")["spend"] == (151, 0.76, False)
    assert a("spend with an unknown cost")["spend"] == (15, 0.1, True)
    assert a("spend text that is not a spend")["spend"] == (0, 0.0, False)
    assert a("rejection not yet answered")["follows_a_rejection:s"] is True
    assert a("rejection then relaunch")["follows_a_rejection:s"] is False
    assert a("two rejections")["rejections:s"] == 2
    assert a("rejection on another step")["rejections:s"] == 0


def test_a_step_with_neither_side_of_a_comparison_answers_false() -> None:
    """submitted and follows_a_rejection compare two positions; a fresh step has neither.
    -1 > -1 is False, but -1 >= -1 would say True: a new step would look already submitted."""
    for name in ("empty", "tool launched", "not isolated", "spend", "plain handoff"):
        got = _engine_answers(JOURNALS[name])
        assert got["follows_a_rejection:s"] is False, name
    assert _engine_answers(JOURNALS["empty"])["submitted:s"] is False
    assert _engine_answers(JOURNALS["tool launched"])["submitted:s"] is False
    # a handoff with no submit, and a submit with no handoff: both are "not submitted back to me"
    assert _engine_answers(JOURNALS["plain handoff"])["submitted:s"] is False
    only_submit = _engine_answers([("step.submitted", "s", "")])
    assert only_submit["submitted:s"] is True
