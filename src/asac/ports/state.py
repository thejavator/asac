"""Port for the state store (docs/reference/state.md).

Evidence and audit are append-only. Gates have a stable ``gate_id``.
Timestamps are passed in by the caller so that adapters stay deterministic.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

GateStatus = Literal["pending", "approved", "rejected", "expired"]


class StateError(Exception):
    """Base class for state errors."""


class NotFound(StateError):
    pass


class RunExists(StateError):
    pass


class EvidenceExists(StateError):
    pass


class GateError(StateError):
    pass


@dataclass(frozen=True)
class RunRecord:
    run_id: str
    pipeline: str
    status: str
    created_at: str


@dataclass(frozen=True)
class EvidenceRecord:
    run_id: str
    evidence_id: str
    produced_by: str
    approved_by: str | None
    bootstrapped: bool
    at: str


@dataclass(frozen=True)
class GateRecord:
    gate_id: str
    run_id: str
    step_id: str
    type: str
    role: str | None
    status: GateStatus
    requested_at: str
    timeout_at: str | None = None
    decided_by: str | None = None
    decided_at: str | None = None
    comment: str | None = None
    evidence_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class AuditRecord:
    seq: int
    at: str
    run_id: str | None
    step_id: str | None
    actor: str
    action: str
    detail: str


class StateStore(Protocol):
    def create_run(self, run_id: str, pipeline: str, at: str) -> None: ...
    def get_run(self, run_id: str) -> RunRecord: ...
    def list_runs(self) -> list[RunRecord]: ...
    def set_run_status(self, run_id: str, status: str) -> None: ...
    def set_step_status(self, run_id: str, step_id: str, status: str) -> None: ...
    def get_step_status(self, run_id: str, step_id: str) -> str | None: ...
    def list_steps(self, run_id: str) -> dict[str, str]: ...
    def add_evidence(
        self,
        run_id: str,
        evidence_id: str,
        produced_by: str,
        at: str,
        approved_by: str | None = None,
        bootstrapped: bool = False,
    ) -> None:
        """Append evidence. Writing the same id twice raises ``EvidenceExists``."""
        ...

    def has_evidence(self, run_id: str, evidence_id: str) -> bool: ...
    def list_evidence(self, run_id: str) -> list[EvidenceRecord]: ...
    def open_gate(self, gate: GateRecord) -> None: ...
    def decide_gate(
        self, gate_id: str, status: GateStatus, decided_by: str, at: str, comment: str | None
    ) -> GateRecord:
        """Only a ``pending`` gate can be decided; otherwise raises ``GateError``."""
        ...

    def reopen_gate(self, gate_id: str) -> GateRecord:
        """Put a rejected gate back to pending. The earlier decision stays in the audit."""
        ...

    def get_gate(self, gate_id: str) -> GateRecord: ...
    def list_gates(self, status: GateStatus | None = None) -> list[GateRecord]: ...
    def append_audit(
        self,
        run_id: str | None,
        actor: str,
        action: str,
        at: str,
        step_id: str | None = None,
        detail: str = "",
    ) -> None: ...
    def audit(self, run_id: str | None = None) -> list[AuditRecord]: ...
