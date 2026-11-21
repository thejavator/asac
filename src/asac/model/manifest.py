"""Layer 1 models: the ``asac.yaml`` manifest (spec v0.4).

Every model forbids unknown keys, so a typo or a v0.5 feature is rejected
instead of being silently ignored.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class Header(_Strict):
    spec: Literal["0.4"]
    workspace: str
    team: str | None = None


class Variable(_Strict):
    type: str = "string"
    description: str | None = None
    sensitive: bool = False
    default: Any = None


class McpServer(_Strict):
    """How a harness reaches this provider as an MCP server (layer-2 extension).

    Exactly one of ``command`` (stdio) or ``url`` (HTTP). ``env`` values must be
    ``${vault...}`` references: secrets are resolved at run time, never stored.
    """

    command: str | None = None
    args: list[str] = Field(default_factory=list)
    url: str | None = None
    env: dict[str, str] = Field(default_factory=dict)


class Provider(_Strict):
    source: str
    version: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    mcp: McpServer | None = None


class Capability(_Strict):
    description: str | None = None
    inputs: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)


class EvidenceType(_Strict):
    description: str | None = None


class Skill(_Strict):
    ref: str
    fulfils: str
    params: dict[str, Any] = Field(default_factory=dict)


class Agent(_Strict):
    skill: str
    provider: str
    harness: str
    tools: list[str] = Field(default_factory=list)
    instructions: list[str] = Field(default_factory=list)
    knowledge: list[str] = Field(default_factory=list)


class Knowledge(_Strict):
    provider: str
    path: str | None = None
    stale_after: str | None = None
    trust_tier: str | None = None


class Instruction(_Strict):
    ref: str


class PerRun(_Strict):
    tokens: int | None = None
    cost_usd: float | None = None
    wall_clock: str | None = None


class PerStep(_Strict):
    iterations: int | None = None


class Budgets(_Strict):
    per_run: PerRun | None = None
    per_step: PerStep | None = None


class HookDefinition(_Strict):
    """A hook is local (``run``) or from a registry (``ref``): exactly one."""

    run: str | None = None
    ref: str | None = None
    on_fail: Literal["block", "warn"] = "block"

    @model_validator(mode="after")
    def _exactly_one_source(self) -> HookDefinition:
        if (self.run is None) == (self.ref is None):
            raise ValueError("a hook must set exactly one of 'run' or 'ref'")
        return self


class Hooks(_Strict):
    definitions: dict[str, HookDefinition] = Field(default_factory=dict)
    pre_tool: list[str] = Field(default_factory=list)
    post_step: list[str] = Field(default_factory=list)


class Trigger(_Strict):
    type: str
    provider: str | None = None
    event: str | None = None
    filter: dict[str, Any] = Field(default_factory=dict)


class Gate(_Strict):
    type: Literal["human", "quality", "automated"]
    role: str | None = None
    policy: str | None = None
    timeout: str | None = None


class Execution(_Strict):
    runner: str | None = None
    sandbox: str | None = None
    fallback: Literal["assist"] | None = None


class Loop(_Strict):
    """Retry the agent until every check passes, with a hard cap. The cap is mandatory."""

    until: list[str] = Field(min_length=1)  # hooks (post_step) that must all pass
    max_iterations: int = Field(ge=1, le=50)


class Step(_Strict):
    capability: str
    agent: str
    mode: Literal["assist", "delegate"] = "assist"
    autonomy: Literal["readonly", "review", "autonomous"] | None = None
    dependsOn: list[str] = Field(default_factory=list)  # noqa: N815 (spec name)
    requiresEvidence: list[str] = Field(default_factory=list)  # noqa: N815
    producesEvidence: list[str] = Field(default_factory=list)  # noqa: N815
    gate: Gate | None = None
    execution: Execution | None = None
    escalation: dict[str, str] | None = None
    policies: list[str] = Field(default_factory=list)
    loop: Loop | None = None


class Pipeline(_Strict):
    description: str | None = None
    timeout: str | None = None
    specLevel: Annotated[int, Field(ge=1, le=3)] | None = None  # noqa: N815
    trigger: Trigger | None = None
    steps: dict[str, Step]


class Manifest(_Strict):
    asac: Header
    variables: dict[str, Variable] = Field(default_factory=dict)
    providers: dict[str, Provider] = Field(default_factory=dict)
    capabilities: dict[str, Capability] = Field(default_factory=dict)
    evidenceTypes: dict[str, EvidenceType] = Field(default_factory=dict)  # noqa: N815
    skills: dict[str, Skill] = Field(default_factory=dict)
    agents: dict[str, Agent] = Field(default_factory=dict)
    knowledge: dict[str, Knowledge] = Field(default_factory=dict)
    instructions: list[Instruction] = Field(default_factory=list)
    budgets: Budgets | None = None
    hooks: Hooks | None = None
    pipelines: dict[str, Pipeline] = Field(default_factory=dict)
