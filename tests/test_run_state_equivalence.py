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


def answers(rows: list[Row]) -> dict[str, Any]:
    """Every question the engine used to ask of the audit, answered by RunState."""
    from asac.engine.run_state import RunState

    st = RunState(_audit(rows))
    out: dict[str, Any] = {"was_isolated": st.isolated}
    out["spend"] = (st.spend.tokens, round(st.spend.cost_usd, 6), st.spend.cost_unknown)
    for s in STEPS:
        out[f"submitted:{s}"] = st.submitted(s)
        out[f"autorun_launched:{s}"] = st.tool_launched(s)
        out[f"turns:{s}"] = st.loop_turns(s)
        out[f"rejections:{s}"] = st.rejection_attempts(s)
        out[f"follows_a_rejection:{s}"] = st.awaiting_relaunch(s)
    return out


# What the engine's seven functions answered on these journals, computed by running them at
# commit 35b1f99 (before they moved). Fixed values, so the proof outlives the old code.
EXPECTED: dict[str, dict[str, Any]] = {
    "empty": {
        "autorun_launched:absent": False,
        "autorun_launched:s": False,
        "autorun_launched:t": False,
        "follows_a_rejection:absent": False,
        "follows_a_rejection:s": False,
        "follows_a_rejection:t": False,
        "rejections:absent": 0,
        "rejections:s": 0,
        "rejections:t": 0,
        "spend": (0, 0.0, False),
        "submitted:absent": False,
        "submitted:s": False,
        "submitted:t": False,
        "turns:absent": 0,
        "turns:s": 0,
        "turns:t": 0,
        "was_isolated": False,
    },
    "handoff then submit": {
        "autorun_launched:absent": False,
        "autorun_launched:s": False,
        "autorun_launched:t": False,
        "follows_a_rejection:absent": False,
        "follows_a_rejection:s": False,
        "follows_a_rejection:t": False,
        "rejections:absent": 0,
        "rejections:s": 0,
        "rejections:t": 0,
        "spend": (0, 0.0, False),
        "submitted:absent": False,
        "submitted:s": True,
        "submitted:t": False,
        "turns:absent": 0,
        "turns:s": 0,
        "turns:t": 0,
        "was_isolated": False,
    },
    "isolated run": {
        "autorun_launched:absent": False,
        "autorun_launched:s": False,
        "autorun_launched:t": False,
        "follows_a_rejection:absent": False,
        "follows_a_rejection:s": False,
        "follows_a_rejection:t": False,
        "rejections:absent": 0,
        "rejections:s": 0,
        "rejections:t": 0,
        "spend": (0, 0.0, False),
        "submitted:absent": False,
        "submitted:s": False,
        "submitted:t": False,
        "turns:absent": 0,
        "turns:s": 0,
        "turns:t": 0,
        "was_isolated": True,
    },
    "isolation failed": {
        "autorun_launched:absent": False,
        "autorun_launched:s": False,
        "autorun_launched:t": False,
        "follows_a_rejection:absent": False,
        "follows_a_rejection:s": False,
        "follows_a_rejection:t": False,
        "rejections:absent": 0,
        "rejections:s": 0,
        "rejections:t": 0,
        "spend": (0, 0.0, False),
        "submitted:absent": False,
        "submitted:s": False,
        "submitted:t": False,
        "turns:absent": 0,
        "turns:s": 0,
        "turns:t": 0,
        "was_isolated": True,
    },
    "iterations": {
        "autorun_launched:absent": False,
        "autorun_launched:s": False,
        "autorun_launched:t": False,
        "follows_a_rejection:absent": False,
        "follows_a_rejection:s": False,
        "follows_a_rejection:t": False,
        "rejections:absent": 0,
        "rejections:s": 0,
        "rejections:t": 0,
        "spend": (0, 0.0, False),
        "submitted:absent": False,
        "submitted:s": False,
        "submitted:t": False,
        "turns:absent": 0,
        "turns:s": 2,
        "turns:t": 1,
        "was_isolated": False,
    },
    "not isolated": {
        "autorun_launched:absent": False,
        "autorun_launched:s": False,
        "autorun_launched:t": False,
        "follows_a_rejection:absent": False,
        "follows_a_rejection:s": False,
        "follows_a_rejection:t": False,
        "rejections:absent": 0,
        "rejections:s": 0,
        "rejections:t": 0,
        "spend": (0, 0.0, False),
        "submitted:absent": False,
        "submitted:s": False,
        "submitted:t": False,
        "turns:absent": 0,
        "turns:s": 0,
        "turns:t": 0,
        "was_isolated": False,
    },
    "plain handoff": {
        "autorun_launched:absent": False,
        "autorun_launched:s": False,
        "autorun_launched:t": False,
        "follows_a_rejection:absent": False,
        "follows_a_rejection:s": False,
        "follows_a_rejection:t": False,
        "rejections:absent": 0,
        "rejections:s": 0,
        "rejections:t": 0,
        "spend": (0, 0.0, False),
        "submitted:absent": False,
        "submitted:s": False,
        "submitted:t": False,
        "turns:absent": 0,
        "turns:s": 0,
        "turns:t": 0,
        "was_isolated": False,
    },
    "rejection not yet answered": {
        "autorun_launched:absent": False,
        "autorun_launched:s": True,
        "autorun_launched:t": False,
        "follows_a_rejection:absent": False,
        "follows_a_rejection:s": True,
        "follows_a_rejection:t": False,
        "rejections:absent": 0,
        "rejections:s": 0,
        "rejections:t": 0,
        "spend": (0, 0.0, False),
        "submitted:absent": False,
        "submitted:s": False,
        "submitted:t": False,
        "turns:absent": 0,
        "turns:s": 0,
        "turns:t": 0,
        "was_isolated": False,
    },
    "rejection on another step": {
        "autorun_launched:absent": False,
        "autorun_launched:s": False,
        "autorun_launched:t": False,
        "follows_a_rejection:absent": False,
        "follows_a_rejection:s": False,
        "follows_a_rejection:t": True,
        "rejections:absent": 0,
        "rejections:s": 0,
        "rejections:t": 0,
        "spend": (0, 0.0, False),
        "submitted:absent": False,
        "submitted:s": False,
        "submitted:t": False,
        "turns:absent": 0,
        "turns:s": 0,
        "turns:t": 0,
        "was_isolated": False,
    },
    "rejection then relaunch": {
        "autorun_launched:absent": False,
        "autorun_launched:s": True,
        "autorun_launched:t": False,
        "follows_a_rejection:absent": False,
        "follows_a_rejection:s": False,
        "follows_a_rejection:t": False,
        "rejections:absent": 0,
        "rejections:s": 1,
        "rejections:t": 0,
        "spend": (0, 0.0, False),
        "submitted:absent": False,
        "submitted:s": False,
        "submitted:t": False,
        "turns:absent": 0,
        "turns:s": 0,
        "turns:t": 0,
        "was_isolated": False,
    },
    "spend": {
        "autorun_launched:absent": False,
        "autorun_launched:s": False,
        "autorun_launched:t": False,
        "follows_a_rejection:absent": False,
        "follows_a_rejection:s": False,
        "follows_a_rejection:t": False,
        "rejections:absent": 0,
        "rejections:s": 0,
        "rejections:t": 0,
        "spend": (151, 0.76, False),
        "submitted:absent": False,
        "submitted:s": False,
        "submitted:t": False,
        "turns:absent": 0,
        "turns:s": 0,
        "turns:t": 0,
        "was_isolated": False,
    },
    "spend text that is not a spend": {
        "autorun_launched:absent": False,
        "autorun_launched:s": False,
        "autorun_launched:t": False,
        "follows_a_rejection:absent": False,
        "follows_a_rejection:s": False,
        "follows_a_rejection:t": False,
        "rejections:absent": 0,
        "rejections:s": 0,
        "rejections:t": 0,
        "spend": (0, 0.0, False),
        "submitted:absent": False,
        "submitted:s": False,
        "submitted:t": False,
        "turns:absent": 0,
        "turns:s": 0,
        "turns:t": 0,
        "was_isolated": False,
    },
    "spend with an unknown cost": {
        "autorun_launched:absent": False,
        "autorun_launched:s": False,
        "autorun_launched:t": False,
        "follows_a_rejection:absent": False,
        "follows_a_rejection:s": False,
        "follows_a_rejection:t": False,
        "rejections:absent": 0,
        "rejections:s": 0,
        "rejections:t": 0,
        "spend": (15, 0.1, True),
        "submitted:absent": False,
        "submitted:s": False,
        "submitted:t": False,
        "turns:absent": 0,
        "turns:s": 0,
        "turns:t": 0,
        "was_isolated": False,
    },
    "submit on another step only": {
        "autorun_launched:absent": False,
        "autorun_launched:s": False,
        "autorun_launched:t": False,
        "follows_a_rejection:absent": False,
        "follows_a_rejection:s": False,
        "follows_a_rejection:t": False,
        "rejections:absent": 0,
        "rejections:s": 0,
        "rejections:t": 0,
        "spend": (0, 0.0, False),
        "submitted:absent": False,
        "submitted:s": False,
        "submitted:t": True,
        "turns:absent": 0,
        "turns:s": 0,
        "turns:t": 0,
        "was_isolated": False,
    },
    "submit, back, submit again": {
        "autorun_launched:absent": False,
        "autorun_launched:s": False,
        "autorun_launched:t": False,
        "follows_a_rejection:absent": False,
        "follows_a_rejection:s": False,
        "follows_a_rejection:t": False,
        "rejections:absent": 0,
        "rejections:s": 0,
        "rejections:t": 0,
        "spend": (0, 0.0, False),
        "submitted:absent": False,
        "submitted:s": True,
        "submitted:t": False,
        "turns:absent": 0,
        "turns:s": 0,
        "turns:t": 0,
        "was_isolated": False,
    },
    "submit, checks fail, handed back": {
        "autorun_launched:absent": False,
        "autorun_launched:s": False,
        "autorun_launched:t": False,
        "follows_a_rejection:absent": False,
        "follows_a_rejection:s": False,
        "follows_a_rejection:t": False,
        "rejections:absent": 0,
        "rejections:s": 0,
        "rejections:t": 0,
        "spend": (0, 0.0, False),
        "submitted:absent": False,
        "submitted:s": False,
        "submitted:t": False,
        "turns:absent": 0,
        "turns:s": 0,
        "turns:t": 0,
        "was_isolated": False,
    },
    "tool launched": {
        "autorun_launched:absent": False,
        "autorun_launched:s": True,
        "autorun_launched:t": False,
        "follows_a_rejection:absent": False,
        "follows_a_rejection:s": False,
        "follows_a_rejection:t": False,
        "rejections:absent": 0,
        "rejections:s": 0,
        "rejections:t": 0,
        "spend": (0, 0.0, False),
        "submitted:absent": False,
        "submitted:s": False,
        "submitted:t": False,
        "turns:absent": 0,
        "turns:s": 0,
        "turns:t": 0,
        "was_isolated": False,
    },
    "tool launched on another step": {
        "autorun_launched:absent": False,
        "autorun_launched:s": False,
        "autorun_launched:t": True,
        "follows_a_rejection:absent": False,
        "follows_a_rejection:s": False,
        "follows_a_rejection:t": False,
        "rejections:absent": 0,
        "rejections:s": 0,
        "rejections:t": 0,
        "spend": (0, 0.0, False),
        "submitted:absent": False,
        "submitted:s": False,
        "submitted:t": False,
        "turns:absent": 0,
        "turns:s": 0,
        "turns:t": 0,
        "was_isolated": False,
    },
    "two rejections": {
        "autorun_launched:absent": False,
        "autorun_launched:s": True,
        "autorun_launched:t": False,
        "follows_a_rejection:absent": False,
        "follows_a_rejection:s": False,
        "follows_a_rejection:t": False,
        "rejections:absent": 0,
        "rejections:s": 2,
        "rejections:t": 0,
        "spend": (0, 0.0, False),
        "submitted:absent": False,
        "submitted:s": False,
        "submitted:t": False,
        "turns:absent": 0,
        "turns:s": 0,
        "turns:t": 0,
        "was_isolated": False,
    },
}


@pytest.mark.parametrize("name", sorted(JOURNALS))
def test_run_state_answers_what_the_engine_functions_answered(name: str) -> None:
    assert answers(JOURNALS[name]) == EXPECTED[name]


def test_every_journal_has_a_pinned_answer() -> None:
    assert set(EXPECTED) == set(JOURNALS)


def test_pinned_answers_for_the_cases_that_matter() -> None:
    a = lambda n: answers(JOURNALS[n])  # noqa: E731
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
    """submitted and awaiting_relaunch compare two positions; a fresh step has neither.
    -1 > -1 is False, but -1 >= -1 would say True: a new step would look already submitted."""
    for name in ("empty", "tool launched", "not isolated", "spend", "plain handoff"):
        assert answers(JOURNALS[name])["follows_a_rejection:s"] is False, name
    assert answers(JOURNALS["empty"])["submitted:s"] is False
    assert answers(JOURNALS["tool launched"])["submitted:s"] is False
    assert answers(JOURNALS["plain handoff"])["submitted:s"] is False
    assert answers([("step.submitted", "s", "")])["submitted:s"] is True


def test_run_state_never_reads_a_database() -> None:
    """It takes entries, not a store: the rules are testable on a list."""
    import inspect

    from asac.engine.run_state import RunState

    assert "store" not in str(inspect.signature(RunState.__init__))


# -- the worktree path, the last reading of the audit text that lived outside RunState ---------


@pytest.mark.parametrize(
    "rows,path",
    [
        ([], None),
        ([("run.created", None, "p")], None),
        ([("workspace.created", None, "branch=asac/r base=abc path=/w/r")], "/w/r"),
        ([("workspace.created", None, "branch=b base=c")], None),  # no path field
        ([("workspace.failed", None, "no git")], None),
        (  # the first creation wins, as the old reader returned on the first match
            [
                ("workspace.created", None, "path=/first"),
                ("workspace.created", None, "path=/second"),
            ],
            "/first",
        ),
    ],
)
def test_the_worktree_is_read_as_the_old_reader_did(rows: list[Row], path: str | None) -> None:
    from pathlib import Path

    from asac.engine.run_state import RunState

    got = RunState(_audit(rows)).workspace
    assert got == (Path(path) if path else None)


def test_recorded_workspace_still_refuses_a_worktree_that_is_gone(tmp_path: Any) -> None:
    """The check that the folder exists stays with the code that touches the disk."""
    from types import SimpleNamespace

    from asac.engine.runtime import recorded_workspace
    from asac.ports.state import StateError

    rows = [("workspace.created", None, f"path={tmp_path / 'gone'}")]
    store = SimpleNamespace(audit=lambda run_id=None: _audit(rows))
    with pytest.raises(StateError, match="missing"):
        recorded_workspace(store, "r")  # type: ignore[arg-type]
    (tmp_path / "gone").mkdir()
    assert recorded_workspace(store, "r") == tmp_path / "gone"  # type: ignore[arg-type]
