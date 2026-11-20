"""Port for telling people something needs them (gate opened, run blocked, ...).

Delivery is best effort: the engine never fails a run because a notification failed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Notification:
    kind: str  # gate.opened | step.blocked | step.escalated | step.failed | run.completed
    title: str
    body: str
    run_id: str
    step_id: str | None = None
    gate_id: str | None = None
    role: str | None = None
    link: str | None = None


class NotifyError(Exception):
    """Delivery failed. The message never contains the target URL or credentials."""


class Notifier(Protocol):
    def send(self, note: Notification) -> None: ...
