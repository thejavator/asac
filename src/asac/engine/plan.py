"""Static plan: the step order, gates and a token estimate. Nothing is executed."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from asac.model import Manifest
from asac.model.manifest import Step

# Heuristic per agent iteration. Real numbers come from the harness at run time.
ESTIMATED_TOKENS_PER_ITERATION = 20_000


def waves(steps: Mapping[str, Step]) -> list[list[str]]:
    """Group steps into waves: every step's dependencies are in earlier waves."""
    done: set[str] = set()
    remaining = list(steps)
    result: list[list[str]] = []
    while remaining:
        ready = [
            s for s in remaining if all(d in done or d not in steps for d in steps[s].dependsOn)
        ]
        if not ready:
            raise ValueError("dependsOn contains a cycle")
        result.append(ready)
        done.update(ready)
        remaining = [s for s in remaining if s not in done]
    return result


def topo_order(steps: Mapping[str, Step]) -> list[str]:
    return [s for wave in waves(steps) for s in wave]


@dataclass(frozen=True)
class PlannedStep:
    id: str
    level: int
    capability: str
    agent: str
    mode: str
    depends_on: tuple[str, ...]
    requires: tuple[str, ...]
    produces: tuple[str, ...]
    gate: str | None
    estimated_tokens: int


@dataclass(frozen=True)
class Plan:
    pipeline: str
    steps: tuple[PlannedStep, ...]
    estimated_tokens: int
    budget_tokens: int | None

    @property
    def levels(self) -> int:
        return 1 + max((s.level for s in self.steps), default=-1)

    @property
    def over_budget(self) -> bool:
        return self.budget_tokens is not None and self.estimated_tokens > self.budget_tokens


def build_plan(manifest: Manifest, pipeline: str) -> Plan:
    pipe = manifest.pipelines[pipeline]
    per_step = manifest.budgets.per_step if manifest.budgets else None
    iterations = per_step.iterations if per_step and per_step.iterations else 1
    planned: list[PlannedStep] = []
    for level, wave in enumerate(waves(pipe.steps)):
        for sid in wave:
            step = pipe.steps[sid]
            gate = None
            if step.gate:
                gate = step.gate.type + (f"({step.gate.role})" if step.gate.role else "")
            planned.append(
                PlannedStep(
                    id=sid,
                    level=level,
                    capability=step.capability,
                    agent=step.agent,
                    mode=step.mode,
                    depends_on=tuple(step.dependsOn),
                    requires=tuple(step.requiresEvidence),
                    produces=tuple(step.producesEvidence),
                    gate=gate,
                    estimated_tokens=iterations * ESTIMATED_TOKENS_PER_ITERATION,
                )
            )
    per_run = manifest.budgets.per_run if manifest.budgets else None
    return Plan(
        pipeline=pipeline,
        steps=tuple(planned),
        estimated_tokens=sum(s.estimated_tokens for s in planned),
        budget_tokens=per_run.tokens if per_run else None,
    )


def render_plan(plan: Plan) -> list[str]:
    lines = [f"pipeline {plan.pipeline}: {len(plan.steps)} steps in {plan.levels} levels"]
    for s in plan.steps:
        gate = f"gate={s.gate}" if s.gate else "no gate"
        lines.append(
            f"  [{s.level}] {s.id:<14} capability={s.capability} agent={s.agent} "
            f"mode={s.mode} {gate}"
        )
        if s.requires:
            lines.append(f"       requires: {', '.join(s.requires)}")
        if s.produces:
            lines.append(f"       produces: {', '.join(s.produces)}")
    budget = f" / budget {plan.budget_tokens:,}" if plan.budget_tokens else ""
    lines.append(f"estimated tokens: {plan.estimated_tokens:,}{budget}")
    if plan.over_budget:
        lines.append("warning: the estimate exceeds the per-run token budget")
    return lines
