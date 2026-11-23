from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from asac.catalog import BUILTIN_POLICIES, HARNESSES
from asac.clock import parse_duration
from asac.model import Manifest, VarsFile
from asac.validate.unapplied import unapplied_in

VAR_RE = re.compile(r"^var\.([A-Za-z_][A-Za-z0-9_]*)$")
VAULT_RE = re.compile(r"^\$\{vault\.[A-Za-z0-9_./-]+\}$")
REGISTRY_RE = re.compile(r"^[a-z0-9.-]+\.[a-z]{2,}/")


class Severity(StrEnum):
    ERROR = "error"
    WARNING = "warning"


@dataclass(frozen=True)
class Issue:
    code: str
    severity: Severity
    path: str
    message: str


def _upstream(pipeline_steps: dict[str, list[str]], step: str) -> set[str]:
    seen: set[str] = set()
    stack = list(pipeline_steps.get(step, []))
    while stack:
        s = stack.pop()
        if s in seen or s not in pipeline_steps:
            continue
        seen.add(s)
        stack.extend(pipeline_steps[s])
    return seen


def _has_cycle(graph: dict[str, list[str]]) -> bool:
    state: dict[str, int] = {}

    def visit(n: str) -> bool:
        if state.get(n) == 1:
            return True
        if state.get(n) == 2:
            return False
        state[n] = 1
        if any(visit(d) for d in graph.get(n, []) if d in graph):
            return True
        state[n] = 2
        return False

    return any(visit(n) for n in graph)


def validate(manifest: Manifest, root: Path, vars_file: VarsFile | None = None) -> list[Issue]:
    issues: list[Issue] = []

    def err(code: str, path: str, msg: str) -> None:
        issues.append(Issue(code, Severity.ERROR, path, msg))

    def warn(code: str, path: str, msg: str) -> None:
        issues.append(Issue(code, Severity.WARNING, path, msg))

    root = root.resolve()

    def check_local(path: str, where: str) -> None:
        target = (root / path).resolve()
        if not target.is_relative_to(root):
            err("ASAC011", where, f"path '{path}' is outside the repository")
        elif not target.exists():
            err("ASAC011", where, f"path '{path}' does not exist")

    # Skills
    for name, skill in manifest.skills.items():
        if skill.fulfils not in manifest.capabilities:
            err("ASAC005", f"skills.{name}.fulfils", f"unknown capability '{skill.fulfils}'")
        if REGISTRY_RE.match(skill.ref):
            warn("ASAC017", f"skills.{name}.ref", "registry reference not resolved (no registry)")
        else:
            check_local(skill.ref, f"skills.{name}.ref")

    # MCP servers on providers
    for name, prov in manifest.providers.items():
        mcp = prov.mcp
        if mcp is None:
            continue
        at = f"providers.{name}.mcp"
        if (mcp.command is None) == (mcp.url is None):
            err("ASAC024", at, "give exactly one of 'command' or 'url'")
        if mcp.url is not None and not mcp.url.startswith("https://"):
            err("ASAC024", f"{at}.url", "MCP url must be https://")
        for key, value in mcp.env.items():
            if not VAULT_RE.match(value):
                err("ASAC025", f"{at}.env.{key}", "secrets must be ${vault...} references")

    # Agents
    for name, agent in manifest.agents.items():
        if agent.skill not in manifest.skills:
            err("ASAC003", f"agents.{name}.skill", f"unknown skill '{agent.skill}'")
        if agent.provider not in manifest.providers:
            err("ASAC004", f"agents.{name}.provider", f"unknown provider '{agent.provider}'")
        for tool in agent.tools:
            if tool not in manifest.providers:
                err("ASAC004", f"agents.{name}.tools", f"unknown provider '{tool}'")

    # Variables referenced as var.*
    declared = set(manifest.variables)

    def resolve_var(value: str, where: str) -> str | None:
        m = VAR_RE.match(value)
        if not m:
            return value
        if m.group(1) not in declared:
            err("ASAC014", where, f"variable '{m.group(1)}' is not declared in 'variables'")
            return None
        if vars_file is None:
            return None
        return str(vars_file.values.get(m.group(1))) if m.group(1) in vars_file.values else None

    for name, prov in manifest.providers.items():
        for key, val in prov.config.items():
            if isinstance(val, str):
                resolve_var(val, f"providers.{name}.config.{key}")

    harness_of: dict[str, str] = {}
    for name, agent in manifest.agents.items():
        h = resolve_var(agent.harness, f"agents.{name}.harness")
        if h is None:
            continue
        if h not in HARNESSES:
            err("ASAC015", f"agents.{name}.harness", f"unknown harness '{h}'")
        else:
            harness_of[name] = h

    # Local paths
    for i, ins in enumerate(manifest.instructions):
        check_local(ins.ref, f"instructions[{i}].ref")
    for name, kn in manifest.knowledge.items():
        if kn.path:
            check_local(kn.path, f"knowledge.{name}.path")

    # Agent references to instructions and knowledge
    known_refs = {ins.ref for ins in manifest.instructions}
    for name, agent in manifest.agents.items():
        for ref in agent.instructions:
            if ref not in known_refs:
                err("ASAC021", f"agents.{name}.instructions", f"'{ref}' is not in 'instructions'")
        for kn_name in agent.knowledge:
            if kn_name not in manifest.knowledge:
                err("ASAC022", f"agents.{name}.knowledge", f"'{kn_name}' is not in 'knowledge'")

    # Durations must parse, otherwise the limit would silently never apply
    def check_duration(value: str | None, where: str) -> None:
        if value:
            try:
                parse_duration(value)
            except ValueError as exc:
                err("ASAC023", where, str(exc))

    if manifest.budgets and manifest.budgets.per_run:
        check_duration(manifest.budgets.per_run.wall_clock, "budgets.per_run.wall_clock")
    for pname, pipe in manifest.pipelines.items():
        check_duration(pipe.timeout, f"pipelines.{pname}.timeout")
        for sname, st in pipe.steps.items():
            if st.gate:
                check_duration(st.gate.timeout, f"pipelines.{pname}.steps.{sname}.gate.timeout")

    # Keys accepted but not applied by this version: said, never silently ignored
    for where, message in unapplied_in(manifest):
        warn("ASAC027", where, message)

    # Hooks
    hooks = manifest.hooks
    if hooks:
        for name, hook in hooks.definitions.items():
            if hook.run:
                check_local(hook.run, f"hooks.definitions.{name}.run")
            elif hook.ref and not REGISTRY_RE.match(hook.ref):
                err("ASAC018", f"hooks.definitions.{name}.ref", "not a registry reference")
            elif hook.ref and "#sha256:" not in hook.ref:
                err(
                    "ASAC019",
                    f"hooks.definitions.{name}.ref",
                    "registry hook needs a #sha256 digest",
                )
        for point in ("pre_tool", "post_step"):
            for hn in getattr(hooks, point):
                if hn not in hooks.definitions:
                    err("ASAC012", f"hooks.{point}", f"unknown hook '{hn}'")

    # Pipelines
    produced_types = set(manifest.evidenceTypes)
    for pname, pipe in manifest.pipelines.items():
        graph = {s: st.dependsOn for s, st in pipe.steps.items()}
        if _has_cycle(graph):
            err("ASAC008", f"pipelines.{pname}", "dependsOn contains a cycle")
            cyclic = True
        else:
            cyclic = False
        for sname, step in pipe.steps.items():
            at = f"pipelines.{pname}.steps.{sname}"
            if step.capability not in manifest.capabilities:
                err("ASAC001", f"{at}.capability", f"unknown capability '{step.capability}'")
            if step.agent not in manifest.agents:
                err("ASAC002", f"{at}.agent", f"unknown agent '{step.agent}'")
            else:
                sk = manifest.skills.get(manifest.agents[step.agent].skill)
                if sk and sk.fulfils != step.capability:
                    err(
                        "ASAC006",
                        f"{at}.agent",
                        f"agent '{step.agent}' fulfils '{sk.fulfils}', "
                        f"step needs '{step.capability}'",
                    )
                h = harness_of.get(step.agent)
                if h and step.mode == "delegate" and not HARNESSES[h].headless:
                    err("ASAC013", f"{at}.mode", f"harness '{h}' is not headless, cannot delegate")
            for d in step.dependsOn:
                if d not in pipe.steps:
                    err("ASAC007", f"{at}.dependsOn", f"unknown step '{d}'")
            for ev in step.requiresEvidence + step.producesEvidence:
                if ev not in produced_types:
                    err("ASAC010", at, f"evidence type '{ev}' is not declared")
            if not cyclic:
                up = _upstream(graph, sname)
                available = {e for u in up for e in pipe.steps[u].producesEvidence}
                for ev in step.requiresEvidence:
                    if ev not in available:
                        err(
                            "ASAC009",
                            f"{at}.requiresEvidence",
                            f"'{ev}' is not produced by any upstream step",
                        )
            for pol in step.policies:
                if pol not in BUILTIN_POLICIES:
                    check_local(f".asac/policies/{pol}.rego", f"{at}.policies")
            if step.hooks is not None:
                known = set(manifest.hooks.definitions) if manifest.hooks else set()
                for point in ("pre_tool", "post_step"):
                    for hn in getattr(step.hooks, point):
                        if hn not in known:
                            err("ASAC012", f"{at}.hooks.{point}", f"unknown hook '{hn}'")
            if step.loop is not None:
                declared_hooks = set(manifest.hooks.definitions) if manifest.hooks else set()
                for check in step.loop.until:
                    if check not in declared_hooks:
                        err("ASAC012", f"{at}.loop.until", f"unknown hook '{check}'")
            if step.gate and step.gate.policy:
                check_local(step.gate.policy, f"{at}.gate.policy")
            if step.gate and step.gate.type in ("human", "quality") and not step.gate.role:
                err("ASAC020", f"{at}.gate", f"{step.gate.type} gate needs a role")
        if pipe.specLevel and pipe.specLevel >= 2 and not cyclic:
            # specLevel 2: a gated step produces evidence that a later step requires.
            consumed = {e for st in pipe.steps.values() for e in st.requiresEvidence}
            gated = any(
                st.gate and set(st.producesEvidence) & consumed for st in pipe.steps.values()
            )
            if not gated:
                warn(
                    "ASAC026",
                    f"pipelines.{pname}.specLevel",
                    "specLevel 2 needs a gated step whose evidence a later step requires",
                )
        if pipe.specLevel == 3:
            # specLevel 3: something machine-checkable runs on the spec (a hook or a policy).
            hooks_on = any(st.hooks is not None for st in pipe.steps.values()) or (
                manifest.hooks is not None
                and bool(manifest.hooks.post_step or manifest.hooks.pre_tool)
            )
            if not hooks_on and not any(st.policies for st in pipe.steps.values()):
                warn(
                    "ASAC026",
                    f"pipelines.{pname}.specLevel",
                    "specLevel 3 needs a hook or a step policy that checks the spec",
                )
    return issues
