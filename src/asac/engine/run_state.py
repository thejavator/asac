"""What a run's audit says about where the run stands.

The audit is the source of truth for a run, and it is written as text. Several decisions of the
engine, and the portal's cost figure, depend on reading it back. That reading lives here, once:
the format of an entry (``tokens=... cost_usd=...``, the names of the events) is known by this
module and by the code that writes it, and by nobody else.

``RunState`` is built from a list of audit entries and does not touch a database, so every rule
below is tested on plain lists. Positions are compared by ``seq``, which the store makes unique
and increasing; a step that has no entry for an event is at -1, and "-1 is after -1" is False.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from asac.engine.governance import Spend
from asac.ports.state import AuditRecord

_ISOLATION_EVENTS = ("workspace.created", "workspace.failed")


class RunState:
    """Read-only view of one run, from its audit entries."""

    def __init__(self, entries: Sequence[AuditRecord]) -> None:
        self._entries = tuple(entries)

    # -- the run -------------------------------------------------------------------------------

    @property
    def isolated(self) -> bool:
        """The run started in a worktree, or tried to: it must never go on without one."""
        return any(a.action in _ISOLATION_EVENTS for a in self._entries)

    @property
    def workspace(self) -> Path | None:
        """The worktree recorded when the run was created. Whether it still exists is not this
        module's question: it reads entries, it does not touch the disk."""
        for a in self._entries:
            if a.action == "workspace.created":
                fields = dict(p.split("=", 1) for p in a.detail.split() if "=" in p)
                if "path" in fields:
                    return Path(fields["path"])
        return None

    @property
    def spend(self) -> Spend:
        """Tokens and cost booked so far. An entry that is not a spend line adds nothing."""
        tokens, cost, unknown = 0, 0.0, False
        for a in self._entries:
            if a.action == "spend.recorded" and a.detail.startswith("tokens="):
                parts = dict(p.split("=", 1) for p in a.detail.split())
                tokens += int(parts["tokens"])
                cost += float(parts["cost_usd"])
                unknown = unknown or parts.get("cost") == "unknown"
        return Spend(tokens=tokens, cost_usd=cost, cost_unknown=unknown)

    # -- one step ------------------------------------------------------------------------------

    def submitted(self, step: str) -> bool:
        """The last hand-over of this step to a person was answered by `asac submit`."""
        return self._last(step, ("step.submitted",)) > self._last(step, ("step.handoff",))

    def tool_launched(self, step: str) -> bool:
        """ASAC has launched the tool for this step at least once, so it can launch it again."""
        return any(a.step_id == step and a.action == "tool.launched" for a in self._entries)

    def loop_turns(self, step: str) -> int:
        """Turns of the step's loop that have been judged so far."""
        return self._count(step, "step.iteration")

    def rejection_attempts(self, step: str) -> int:
        """Launches made after a rejection, whatever their outcome (a blocked one still counts)."""
        return self._count(step, "attempt.after_rejection")

    def awaiting_relaunch(self, step: str) -> bool:
        """The last rejection of this step has not been answered by a launch yet."""
        answered = self._last(step, ("tool.launched", "attempt.after_rejection"))
        return self._last(step, ("rejection.handled",)) > answered

    # -- helpers -------------------------------------------------------------------------------

    def _last(self, step: str, actions: tuple[str, ...]) -> int:
        seqs = [a.seq for a in self._entries if a.step_id == step and a.action in actions]
        return max(seqs, default=-1)

    def _count(self, step: str, action: str) -> int:
        return sum(1 for a in self._entries if a.step_id == step and a.action == action)
