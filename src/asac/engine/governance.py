"""Governance checks: budgets, autonomy, escalation, kill switch and policies.

Each check returns a verdict. The engine decides what a verdict means for the run,
so the same logic applies to assist and delegate steps.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from asac import clock
from asac.catalog import BUILTIN_POLICIES
from asac.clock import parse_duration, parse_ts
from asac.model import Manifest
from asac.model.manifest import Step
from asac.ports.policy import PolicyEngine
from asac.ports.state import StateStore

ALLOW = "allow"
BLOCK = "block"  # stop the run, exit 3
ESCALATE = "escalate"  # wait for a human, exit 2


@dataclass(frozen=True)
class Verdict:
    action: str
    reason: str = ""


@dataclass
class Spend:
    tokens: int = 0
    cost_usd: float = 0.0
    iterations: int = 0
    by_step: dict[str, int] = field(default_factory=dict)


def is_killed(store: StateStore, run_id: str) -> bool:
    return store.get_run(run_id).status == "killed"


def check_budget(manifest: Manifest, spent: Spend) -> Verdict:
    """Per-run ceilings. Exceeding one blocks the run."""
    b = manifest.budgets
    if b is None or b.per_run is None:
        return Verdict(ALLOW)
    pr = b.per_run
    if pr.tokens is not None and spent.tokens > pr.tokens:
        return Verdict(BLOCK, f"token budget exceeded ({spent.tokens:,} > {pr.tokens:,})")
    if pr.cost_usd is not None and spent.cost_usd > pr.cost_usd:
        return Verdict(BLOCK, f"cost budget exceeded (${spent.cost_usd:.2f} > ${pr.cost_usd:.2f})")
    return Verdict(ALLOW)


def check_iterations(manifest: Manifest, iterations: int) -> Verdict:
    b = manifest.budgets
    if b is None or b.per_step is None or b.per_step.iterations is None:
        return Verdict(ALLOW)
    if iterations > b.per_step.iterations:
        return Verdict(BLOCK, f"iteration budget exceeded ({iterations} > {b.per_step.iterations})")
    return Verdict(ALLOW)


def check_autonomy(manifest: Manifest, step: Step) -> Verdict:
    """``autonomous`` needs a written doctrine: at least one instruction must be declared."""
    if step.autonomy == "autonomous" and not manifest.instructions:
        return Verdict(BLOCK, "autonomy 'autonomous' requires a declared instruction (doctrine)")
    return Verdict(ALLOW)


def permission_for(step: Step) -> str:
    """Mode handed to the harness. ``readonly`` never lets the agent write."""
    if step.autonomy == "readonly":
        return "readonly"
    return step.mode


def check_escalation(step: Step, reported: list[str]) -> Verdict:
    """The harness reports reasons it could not handle. Each reason maps to a target."""
    if not reported or not step.escalation:
        return Verdict(ALLOW)
    for reason in reported:
        target = step.escalation.get(reason)
        if target == "human":
            return Verdict(ESCALATE, f"escalated to human: {reason}")
    unknown = [r for r in reported if r not in step.escalation]
    if unknown:
        return Verdict(BLOCK, f"no escalation rule for: {', '.join(unknown)}")
    return Verdict(ALLOW)


def check_policies(
    step: Step, engine: PolicyEngine | None, input_: dict[str, Any], root: Path
) -> Verdict:
    """Run the step's gate policy and its named policies (built-in or ``.asac/policies``).

    Fail closed: if the policy engine cannot run, the step is blocked, never waved through.
    """
    if not step.policies and not (step.gate and step.gate.policy):
        return Verdict(ALLOW)
    if engine is None:
        return Verdict(BLOCK, "policy declared but no policy engine is configured")
    files: list[str] = []
    if step.gate and step.gate.policy:
        files.append(step.gate.policy)
    for name in step.policies:
        if name in BUILTIN_POLICIES:
            verdict = _builtin(name, input_)
            if verdict.action != ALLOW:
                return verdict
        else:
            files.append(f".asac/policies/{name}.rego")
    escalate = False
    for path in files:
        try:
            decision = engine.evaluate(path, _package(root, path), input_)
        except Exception as exc:  # engine missing, policy unreadable, opa crashed
            return Verdict(BLOCK, f"policy engine unavailable for '{path}': {exc}")
        if decision.block:
            return Verdict(BLOCK, "; ".join(decision.block))
        escalate = escalate or decision.escalate
    return Verdict(ESCALATE, "policy requests escalation") if escalate else Verdict(ALLOW)


def _builtin(name: str, input_: dict[str, Any]) -> Verdict:
    if name == "no_regression":
        # A score must not decrease. Needs previous and current scores.
        prev, cur = input_.get("previous_score"), input_.get("score")
        if isinstance(prev, (int, float)) and isinstance(cur, (int, float)) and cur < prev:
            return Verdict(BLOCK, f"no_regression: score fell from {prev} to {cur}")
    return Verdict(ALLOW)


def check_wall_clock(manifest: Manifest, started_at: str) -> Verdict:
    """``budgets.per_run.wall_clock``: elapsed time since the run was created."""
    b = manifest.budgets
    if b is None or b.per_run is None or not b.per_run.wall_clock:
        return Verdict(ALLOW)
    limit = parse_duration(b.per_run.wall_clock)
    if clock.now() - parse_ts(started_at) > limit:
        return Verdict(BLOCK, f"wall-clock budget exceeded (> {b.per_run.wall_clock})")
    return Verdict(ALLOW)


def check_pipeline_timeout(timeout: str | None, started_at: str) -> Verdict:
    """``pipeline.timeout``: elapsed time since the run was created."""
    if timeout and clock.now() - parse_ts(started_at) > parse_duration(timeout):
        return Verdict(BLOCK, f"pipeline timeout exceeded (> {timeout})")
    return Verdict(ALLOW)


_PACKAGE = re.compile(r"^package\s+([\w.]+)", re.M)


def _package(root: Path, policy_path: str) -> str:
    """The Rego package declared in the file, e.g. ``asac.gates.qa``."""
    try:
        text = (root / policy_path).read_text(encoding="utf-8")
    except OSError:
        return "main"
    m = _PACKAGE.search(text)
    return m.group(1) if m else "main"
