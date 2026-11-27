"""The organisation overview: what every project's runs say, summed across projects.

Everything here is read from each project's audit, through the same reading the engine uses
(``RunState`` for spend). Nothing is verified: these runs ran on workstations or workers that
report their own events, so every figure is *declared* (see docs/design/portail-entreprise.md,
section 4). The portal shows that label next to each number; a verified figure needs the
central verifier, which does not exist yet.

The functions take plain lists of records, so every rule is tested without a database.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from asac.engine.run_state import RunState
from asac.ports.state import AuditRecord, RunRecord

# Run statuses grouped the way the overview counts them.
ACTIVE = ("running", "gate_waiting")
PROBLEM = ("blocked", "failed", "killed")

# Audit events that a person responsible for compliance must see, whatever the outcome.
SECURITY_EVENTS = ("integrity.violated", "sandbox.denied")


@dataclass(frozen=True)
class ProjectFigures:
    """One project's numbers, from its runs and their audit."""

    project_id: str
    name: str
    team: str | None
    runs: int = 0
    active: int = 0
    completed: int = 0
    problems: int = 0
    pending_gates: int = 0
    cost_usd: float = 0.0
    tokens: int = 0
    cost_unknown_runs: int = 0
    integrity_violations: int = 0
    sandbox_denials: int = 0
    hooks_passed: int = 0
    hooks_failed: int = 0
    unavailable: bool = False

    @property
    def check_pass_rate(self) -> float | None:
        """Share of hook runs that passed, or None when no hook has run."""
        total = self.hooks_passed + self.hooks_failed
        return None if total == 0 else self.hooks_passed / total


@dataclass(frozen=True)
class Overview:
    projects: tuple[ProjectFigures, ...] = field(default_factory=tuple)

    def total(self, name: str) -> float:
        return sum(float(getattr(p, name)) for p in self.projects if not p.unavailable)


def figures_for(
    project_id: str,
    name: str,
    team: str | None,
    runs: Sequence[RunRecord],
    audit_of: Iterable[tuple[str, Sequence[AuditRecord]]],
    pending_gates: int,
) -> ProjectFigures:
    """Sum one project's runs. ``audit_of`` yields (run_id, entries) for each run."""
    cost, tokens, unknown = 0.0, 0, 0
    integrity = denials = passed = failed = 0
    for _run_id, entries in audit_of:
        spend = RunState(entries).spend
        cost += spend.cost_usd
        tokens += spend.tokens
        unknown += 1 if spend.cost_unknown else 0
        for a in entries:
            if a.action == "integrity.violated":
                integrity += 1
            elif a.action == "sandbox.denied":
                denials += 1
            elif a.action == "hook.passed":
                passed += 1
            elif a.action == "hook.failed":
                failed += 1
    return ProjectFigures(
        project_id=project_id,
        name=name,
        team=team,
        runs=len(runs),
        active=sum(r.status in ACTIVE for r in runs),
        completed=sum(r.status == "completed" for r in runs),
        problems=sum(r.status in PROBLEM for r in runs),
        pending_gates=pending_gates,
        cost_usd=round(cost, 4),
        tokens=tokens,
        cost_unknown_runs=unknown,
        integrity_violations=integrity,
        sandbox_denials=denials,
        hooks_passed=passed,
        hooks_failed=failed,
    )


def unavailable(project_id: str, name: str, team: str | None) -> ProjectFigures:
    """A project whose state cannot be read: shown, never silently dropped."""
    return ProjectFigures(project_id=project_id, name=name, team=team, unavailable=True)


__all__ = ["ACTIVE", "PROBLEM", "SECURITY_EVENTS", "Overview", "ProjectFigures", "figures_for",
           "unavailable"]  # fmt: skip
