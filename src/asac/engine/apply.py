"""Apply: stateless execution over a persistent state, resumable after a gate.

``execute`` never waits. When it reaches a gate it persists the state and returns
``Exit.WAITING``. A later call (``asac apply --resume``) continues from there.
"""

from __future__ import annotations

import hashlib
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path
from typing import Any, Literal

from asac import clock
from asac.clock import fmt, now_iso, parse_duration, parse_ts
from asac.engine.governance import (
    ALLOW,
    ESCALATE,
    Spend,
    Verdict,
    check_autonomy,
    check_budget,
    check_escalation,
    check_iterations,
    check_pipeline_timeout,
    check_policies,
    check_wall_clock,
    is_killed,
    permission_for,
)
from asac.engine.integrity import changed, snapshot
from asac.engine.locked import LockedStore
from asac.engine.plan import waves
from asac.engine.run_state import RunState
from asac.engine.workspace import WorkspaceError, commit_step
from asac.hooks import HookError, run_hooks, run_hooks_named
from asac.model import Manifest
from asac.model.manifest import Gate, Pipeline, Step
from asac.ports.artifacts import ArtifactError, ArtifactStore
from asac.ports.harness import Harness
from asac.ports.notifier import Notification, Notifier, NotifyError
from asac.ports.policy import PolicyEngine
from asac.ports.runner import Runner
from asac.ports.state import GateRecord, NotFound, RunExists, RunRecord, StateError, StateStore


class Exit(IntEnum):
    COMPLETED = 0
    ERROR = 1
    WAITING = 2
    BLOCKED = 3


class Forbidden(Exception):
    """The approver does not hold the role the gate requires (exit code 3)."""


@dataclass(frozen=True)
class Outcome:
    code: Exit
    run_id: str
    message: str
    gates: tuple[str, ...] = ()


@dataclass
class Context:
    manifest: Manifest
    pipeline_name: str
    store: StateStore
    harness_for: Callable[..., Harness]  # (agent, run_id) -> the harness of that run
    actor: str = "cli"
    root: Path | None = None
    policy_engine: PolicyEngine | None = None
    runner: Runner | None = None
    notifier: Notifier | None = None
    artifacts: ArtifactStore | None = None
    retries: int = 0  # extra attempts after a failed harness or runner step (0 to 5)
    parallel: int = 1  # independent steps of a wave run together, up to this many (1 to 8)
    lock: threading.RLock = field(default_factory=threading.RLock)  # guards harness set-up
    # Creates the run's worktree and returns (path, branch, base sha), or None when the run
    # is not isolated. Called once, when the run is created.
    workspace: Callable[[str], tuple[Path, str, str] | None] | None = None
    # The worktree of a run, or None when it is not isolated (hooks run there).
    workdir_for: Callable[[str], Path | None] | None = None
    state_dir: Path | None = None  # where briefs live (loops write feedback into them)
    autorun: bool = False  # ASAC launches the tool itself: it can relaunch the agent

    @property
    def pipeline(self) -> Pipeline:
        return self.manifest.pipelines[self.pipeline_name]


def gate_id_for(run_id: str, step_id: str) -> str:
    return f"gate_{run_id}_{step_id}"


def create_run(ctx: Context, run_id: str) -> None:
    at = now_iso()
    try:
        ctx.store.create_run(run_id, ctx.pipeline_name, at)
    except RunExists:
        if ctx.store.get_run(run_id).pipeline != ctx.pipeline_name:
            raise StateError(f"run '{run_id}' belongs to another pipeline") from None
        return
    ctx.store.append_audit(run_id, ctx.actor, "run.created", at, detail=ctx.pipeline_name)
    if ctx.workspace is None:
        return
    try:
        made = ctx.workspace(run_id)
    except Exception as exc:  # no worktree means no isolation: the run must not start
        ctx.store.set_run_status(run_id, "failed")
        ctx.store.append_audit(run_id, ctx.actor, "workspace.failed", now_iso(), detail=str(exc))
        raise StateError(f"cannot isolate run '{run_id}': {exc}") from None
    if made is not None:
        path, branch, base = made
        ctx.store.append_audit(
            run_id, ctx.actor, "workspace.created", now_iso(),
            detail=f"branch={branch} base={base} path={path}",
        )  # fmt: skip


def execute(ctx: Context, run_id: str, only: str | None = None) -> Outcome:
    pipe = ctx.pipeline
    store = ctx.store
    if only is not None and only not in pipe.steps:
        raise StateError(f"unknown step '{only}'")
    rec = store.get_run(run_id)
    if rec.status == "killed":
        return Outcome(Exit.BLOCKED, run_id, "run was killed; it cannot be resumed")
    if ctx.workdir_for is not None and ctx.workspace is not None:
        # An isolated run whose worktree is gone must not advance: the agent would work unisolated.
        try:
            recorded = ctx.workdir_for(run_id)
        except StateError as exc:
            return Outcome(Exit.ERROR, run_id, f"cannot resume {run_id}: {exc}")
        if recorded is None and RunState(store.audit(run_id)).isolated:
            return Outcome(
                Exit.ERROR, run_id,
                f"cannot resume {run_id}: its worktree was never created (isolation required)",
            )  # fmt: skip
    store.set_run_status(run_id, "running")
    parallel = ctx.parallel > 1 and only is None
    if parallel:
        ctx.store = LockedStore(store)  # one connection, shared by the worker threads
    groups = [[only]] if only is not None else waves(pipe.steps)
    for wave in groups:
        deferred: list[str] = []
        for sid in wave:
            out = _advance(ctx, run_id, sid, rec, deferred if parallel else None)
            if out is not None:
                return out
        if deferred:
            out = _run_parallel(ctx, run_id, deferred)
            if out is not None:
                return out
    if all(ctx.store.get_step_status(run_id, s) == "completed" for s in pipe.steps):
        ctx.store.set_run_status(run_id, "completed")
        _audit(ctx, run_id, "run.completed", None)
        return Outcome(Exit.COMPLETED, run_id, "completed")
    return Outcome(Exit.COMPLETED, run_id, f"step {only} completed")


def _run_parallel(ctx: Context, run_id: str, sids: list[str]) -> Outcome | None:
    """Run independent steps of one wave at the same time; the first stop (in order) wins."""
    pipe = ctx.pipeline
    if len(sids) == 1:
        return _run_step(ctx, run_id, sids[0], pipe.steps[sids[0]])
    with ThreadPoolExecutor(max_workers=min(ctx.parallel, len(sids))) as pool:
        futures = [pool.submit(_run_step, ctx, run_id, s, pipe.steps[s]) for s in sids]
        results = [f.result() for f in futures]
    return next((r for r in results if r is not None), None)


def _advance(
    ctx: Context, run_id: str, sid: str, rec: RunRecord, defer: list[str] | None
) -> Outcome | None:
    """One step of the loop. With ``defer`` a step that is ready to run is queued, not run."""
    store, pipe = ctx.store, ctx.pipeline
    if is_killed(store, run_id):
        return Outcome(Exit.BLOCKED, run_id, "run was killed")
    step = pipe.steps[sid]
    status = store.get_step_status(run_id, sid) or "pending"
    if status == "completed":
        return None
    if status not in ("gate_waiting", "handoff"):
        clock_check = check_wall_clock(ctx.manifest, rec.created_at)
        if clock_check.action == ALLOW:
            clock_check = check_pipeline_timeout(pipe.timeout, rec.created_at)
        if clock_check.action != ALLOW:
            return _govern(ctx, run_id, sid, clock_check)
    if status == "handoff":
        return _check_handoff(ctx, run_id, sid, step)
    if status == "gate_waiting":
        rejected = _rejected_gate(ctx, run_id, sid)
        if rejected is not None and _can_relaunch_after_rejection(ctx, run_id, sid, step):
            # The reviewer rejected with a reason and attempts remain: the agent goes again.
            _retry_after_rejection(ctx, run_id, sid, step, rejected)
            return _run_step(ctx, run_id, sid, step)
        return _resolve_gate(ctx, run_id, sid, step)
    unmet = [d for d in step.dependsOn if store.get_step_status(run_id, d) != "completed"]
    if unmet:
        return _block(ctx, run_id, sid, f"dependencies not completed: {', '.join(unmet)}", False)
    missing = [e for e in step.requiresEvidence if not store.has_evidence(run_id, e)]
    if missing:
        return _block(ctx, run_id, sid, f"missing evidence: {', '.join(missing)}", True)
    autonomy = check_autonomy(ctx.manifest, step)
    if autonomy.action != ALLOW:
        return _govern(ctx, run_id, sid, autonomy)
    if defer is not None:
        defer.append(sid)
        return None
    return _run_step(ctx, run_id, sid, step)


def _state(ctx: Context, run_id: str) -> RunState:
    """The run as its audit says it stands right now (read again at every call: it changes)."""
    return RunState(ctx.store.audit(run_id))


def _audit(ctx: Context, run_id: str, action: str, step: str | None, detail: str = "") -> None:
    ctx.store.append_audit(run_id, ctx.actor, action, now_iso(), step_id=step, detail=detail)


def _notify(ctx: Context, run_id: str, sid: str | None, kind: str, title: str, **kw: str) -> None:
    """Best effort: a broken notification channel never changes the outcome of a run."""
    if ctx.notifier is None:
        return
    try:
        ctx.notifier.send(Notification(kind, title, kw.pop("body", ""), run_id, sid, **kw))
    except NotifyError as exc:
        _audit(ctx, run_id, "notify.failed", sid, str(exc))


def _fail(ctx: Context, run_id: str, sid: str, reason: str) -> Outcome:
    ctx.store.set_step_status(run_id, sid, "failed")
    ctx.store.set_run_status(run_id, "failed")
    _audit(ctx, run_id, "step.failed", sid, reason)
    _notify(ctx, run_id, sid, "step.failed", f"Run {run_id} failed at {sid}", body=reason)
    return Outcome(Exit.ERROR, run_id, f"failed at {sid}: {reason}")


def _block(ctx: Context, run_id: str, sid: str, reason: str, run_blocked: bool) -> Outcome:
    ctx.store.set_step_status(run_id, sid, "blocked")
    if run_blocked:
        ctx.store.set_run_status(run_id, "blocked")
    _audit(ctx, run_id, "step.blocked", sid, reason)
    _notify(ctx, run_id, sid, "step.blocked", f"Run {run_id} blocked at {sid}", body=reason)
    return Outcome(Exit.BLOCKED, run_id, f"blocked at {sid}: {reason}")


def _complete(ctx: Context, run_id: str, sid: str, step: Step, approved_by: str | None) -> None:
    at = now_iso()
    for ev in step.producesEvidence:
        # Idempotent: a crash after this point must not duplicate evidence on resume.
        if not ctx.store.has_evidence(run_id, ev):
            ctx.store.add_evidence(run_id, ev, produced_by=sid, at=at, approved_by=approved_by)
            _audit(ctx, run_id, "evidence.produced", sid, ev)
    ctx.store.set_step_status(run_id, sid, "completed")
    _audit(ctx, run_id, "step.completed", sid)


def _run_step(ctx: Context, run_id: str, sid: str, step: Step) -> Outcome | None:
    agent = ctx.manifest.agents[step.agent]
    skill_key = agent.skill
    task = {
        "step": sid,
        "capability": step.capability,
        "agent": step.agent,
        "mode": step.mode,
        "skill": skill_key,
        "produces": list(step.producesEvidence),
    }
    ctx.store.set_step_status(run_id, sid, "running")
    _audit(ctx, run_id, "step.started", sid, step.agent)
    placed, handle = _place(ctx, run_id, sid, step)
    if placed is not None:
        return placed
    try:
        attempt = 0
        while True:
            out = _run_harness(ctx, run_id, sid, step, task, handle)
            while _agent_owes_another_turn(ctx, run_id, sid, step, out):
                # autorun: nobody is at the keyboard, so ASAC relaunches the agent itself, with
                # the reason the previous turn was rejected already written into its brief.
                ctx.store.set_step_status(run_id, sid, "running")
                ctx.store.set_run_status(run_id, "running")
                out = _run_harness(ctx, run_id, sid, step, task, handle)
            if out is None or out.code != Exit.ERROR or attempt >= ctx.retries:
                return out
            attempt += 1
            _audit(ctx, run_id, "step.retry", sid, f"attempt {attempt + 1} of {ctx.retries + 1}")
            ctx.store.set_step_status(run_id, sid, "running")
            ctx.store.set_run_status(run_id, "running")
    finally:
        if handle is not None and ctx.runner is not None:
            ctx.runner.stop(handle)
            _audit(ctx, run_id, "runner.stopped", sid, handle)


def _run_harness(
    ctx: Context, run_id: str, sid: str, step: Step, task: dict[str, Any], handle: str | None = None
) -> Outcome | None:
    state = _state(ctx, run_id)
    if state.awaiting_relaunch(sid):
        _audit(ctx, run_id, "attempt.after_rejection", sid,
               f"launch {state.rejection_attempts(sid) + 1}")  # fmt: skip
    skill_key = task["skill"]
    permission = permission_for(step)
    task["permission"] = permission
    if ctx.root is not None:
        blocked = _run_hooks(ctx, run_id, sid, "pre_tool")
        if blocked is not None:
            return blocked
    rules_before = snapshot(ctx.root) if ctx.root is not None else {}
    try:
        with ctx.lock:  # a harness instance holds per-step state: set-up and run go one at a time
            harness = ctx.harness_for(step.agent, run_id)
            harness.mount(skill_key)
            wanted = list(ctx.manifest.agents[step.agent].tools)
            harness.tools(wanted)
            exposed = [t for t in wanted if ctx.manifest.providers[t].mcp is not None]
            if exposed:  # names only: secrets are never part of the audit
                _audit(ctx, run_id, "tools.exposed", sid, ",".join(exposed))
            harness.permissions(permission)
            result = harness.run(task, {"run_id": run_id, "pipeline": ctx.pipeline_name})
    except Exception as exc:  # any harness failure fails the step, and the run stays resumable
        return _fail(ctx, run_id, sid, str(exc))
    if result.get("status") == "error":
        return _fail(ctx, run_id, sid, str(result.get("message", "harness reported an error")))
    if result.get("status") == "delegated":
        failed = _exec_in_runner(ctx, run_id, sid, step, result, handle)
        if failed is not None:
            return failed
    spend = _record_spend(ctx, run_id, sid, result)
    budget = check_budget(ctx.manifest, spend)
    if budget.action != ALLOW:
        return _govern(ctx, run_id, sid, budget)
    iters = check_iterations(ctx.manifest, int(str(result.get("iterations", 1))))
    if iters.action != ALLOW:
        return _govern(ctx, run_id, sid, iters)
    escalation = check_escalation(step, [str(r) for r in _as_list(result.get("escalate"))])
    if escalation.action != ALLOW:
        return _govern(ctx, run_id, sid, escalation)
    if ctx.root is not None:
        touched = changed(rules_before, snapshot(ctx.root))
        if touched:
            _audit(ctx, run_id, "integrity.violated", sid, ", ".join(touched))
            return _block(
                ctx,
                run_id,
                sid,
                f"the rules were modified during the step: {', '.join(touched)}",
                True,
            )
        _audit(ctx, run_id, "integrity.verified", sid, f"{len(rules_before)} rule files unchanged")
    launched = result.get("autorun")
    if isinstance(launched, dict):
        # ASAC ran the tool itself: no manual hand-off. Hooks check the result, then the gate.
        _audit(
            ctx, run_id, "tool.launched", sid,
            f"{launched.get('tool')} exit={launched.get('exit')} "
            f"log={launched.get('log')} sha256={launched.get('log_sha256')}",
        )  # fmt: skip
        for d in launched.get("denials") or []:
            # What the OS sandbox refused the tool, as the tool and srt reported it
            _audit(ctx, run_id, "sandbox.denied", sid, f"{d['kind']} {d['target']}")
    elif result.get("status") == "handoff":
        return _handoff(ctx, run_id, sid, str(result.get("brief", "")))
    if ctx.root is not None and (step.policies or (step.gate and step.gate.policy)):
        policy = check_policies(step, ctx.policy_engine, _policy_input(result), ctx.root)
        if policy.action != ALLOW:
            return _govern(ctx, run_id, sid, policy)
    return _finish_step(ctx, run_id, sid, step)


OUTPUT_LIMIT = 8000  # characters kept in the audit; the sha256 covers the full output


def _exec_in_runner(
    ctx: Context, run_id: str, sid: str, step: Step, result: dict[str, Any], handle: str | None
) -> Outcome | None:
    """Run the command the harness asked for inside the runner and record what it printed."""
    argv = result.get("exec")
    if handle is None or ctx.runner is None or not isinstance(argv, list) or not argv:
        return _fail(ctx, run_id, sid, "harness delegated the step but no runner is placed")
    timeout = 900
    if ctx.pipeline.timeout:
        timeout = max(1, min(timeout, int(parse_duration(ctx.pipeline.timeout).total_seconds())))
    res = ctx.runner.exec(handle, [str(a) for a in argv], timeout)
    out = res.stdout + (("\n[stderr]\n" + res.stderr) if res.stderr else "")
    _read_tool_report(res.stdout, result)
    digest = hashlib.sha256(out.encode()).hexdigest()
    kept = out[:OUTPUT_LIMIT] + ("\n[truncated]" if len(out) > OUTPUT_LIMIT else "")
    _audit(ctx, run_id, "runner.output", sid, f"exit={res.exit_code} sha256={digest}\n{kept}")
    if ctx.artifacts is not None:  # the full output, not the truncated audit copy
        try:
            name = f"{sid}-output.txt"
            art = ctx.artifacts.put(run_id, sid, name, out.encode(), now_iso())
            _audit(
                ctx, run_id, "artifact.stored", sid, f"{art.name} {art.size} sha256={art.sha256}"
            )
        except ArtifactError as exc:
            _audit(ctx, run_id, "artifact.refused", sid, str(exc))
    if res.exit_code != 0:
        reason = "timed out" if res.exit_code == 124 else f"exited with {res.exit_code}"
        return _fail(ctx, run_id, sid, f"runner command {reason}")
    if result.get("cost") == "error":
        return _fail(ctx, run_id, sid, f"'{argv[0]}' reported an error; see the runner output")
    # ASAC launched the tool, as under autorun: the loop and a rejection can relaunch it.
    _audit(ctx, run_id, "tool.launched", sid, f"{argv[0]} exit=0 runner sha256={digest}")
    return None


def _read_tool_report(stdout: str, result: dict[str, Any]) -> None:
    """Put the cost and tokens the tool printed into ``result``, where the engine books them.

    An output with no report, or a report with no cost, is *unknown*: never booked as zero.
    """
    from asac.adapters.claude_code import parse_claude_report

    try:
        report = parse_claude_report(stdout)
    except ValueError:
        result["cost_unknown"] = True
        return
    if report.is_error:
        result["cost"] = "error"
    result["tokens"] = report.tokens
    if report.cost_usd is None:
        result["cost_unknown"] = True
    else:
        result["cost_usd"] = report.cost_usd


def _place(ctx: Context, run_id: str, sid: str, step: Step) -> tuple[Outcome | None, str | None]:
    """Delegate steps that declare a runner go through the Runner port.

    No capacity: ``fallback: assist`` hands the step to a person, otherwise it is blocked.
    Returns (outcome to stop with, runner handle to stop after the step).
    """
    if step.mode != "delegate" or step.execution is None or step.execution.runner is None:
        return None, None
    if ctx.runner is None or not ctx.runner.available():
        if step.execution.fallback == "assist":
            _audit(ctx, run_id, "runner.unavailable", sid, "fallback: assist")
            return _handoff(ctx, run_id, sid, "runner unavailable, fallback to assist"), None
        return _block(ctx, run_id, sid, "no runner available and no fallback", True), None
    try:
        handle = ctx.runner.start(run_id, sid)
    except RuntimeError as exc:
        return _fail(ctx, run_id, sid, str(exc)), None
    network = getattr(ctx.runner, "network", None)  # the runner says what it is wired to
    detail = f"{handle} network={network}" if network else handle
    _audit(ctx, run_id, "runner.started", sid, detail)
    return None, handle


def _record_spend(ctx: Context, run_id: str, sid: str, result: dict[str, object]) -> Spend:
    """Accumulate the run's spend from the harness report (tokens, cost, iterations)."""
    tokens = int(str(result.get("tokens", 0) or 0))
    cost = float(str(result.get("cost_usd", 0.0) or 0.0))
    unknown = bool(result.get("cost_unknown"))
    total = _state(ctx, run_id).spend  # what was booked before this step
    total.tokens += tokens
    total.cost_usd += cost
    total.cost_unknown = total.cost_unknown or unknown
    detail = f"tokens={tokens} cost_usd={cost:.4f}" + (" cost=unknown" if unknown else "")
    _audit(ctx, run_id, "spend.recorded", sid, detail)
    return total


def _as_list(value: object) -> list[object]:
    return list(value) if isinstance(value, list | tuple) else []


def _policy_input(result: dict[str, object]) -> dict[str, Any]:
    return {k: v for k, v in result.items() if k not in ("status", "brief")}


def _govern(ctx: Context, run_id: str, sid: str, verdict: Verdict) -> Outcome:
    """Apply a governance verdict: block stops the run (3), escalate waits for a human (2)."""
    if verdict.action == ESCALATE:
        _open_escalation_gate(ctx, run_id, sid, verdict.reason)
        ctx.store.set_step_status(run_id, sid, "gate_waiting")
        ctx.store.set_run_status(run_id, "gate_waiting")
        _audit(ctx, run_id, "step.escalated", sid, verdict.reason)
        _notify(ctx, run_id, sid, "step.escalated", f"Run {run_id} needs a person at {sid}",
                body=verdict.reason)  # fmt: skip
        return Outcome(Exit.WAITING, run_id, f"{sid} escalated: {verdict.reason}")
    return _block(ctx, run_id, sid, verdict.reason, True)


def escalation_gate_id(run_id: str, step_id: str) -> str:
    return f"{gate_id_for(run_id, step_id)}_escalation"


def _open_escalation_gate(ctx: Context, run_id: str, sid: str, reason: str) -> None:
    """An escalation is a decision somebody must take, so it has a gate they can answer."""
    gid = escalation_gate_id(run_id, sid)
    try:
        ctx.store.get_gate(gid)
        return
    except NotFound:
        pass
    step = ctx.pipeline.steps[sid]
    ctx.store.open_gate(
        GateRecord(
            gate_id=gid,
            run_id=run_id,
            step_id=sid,
            type="human",
            role=step.gate.role if step.gate else None,
            status="pending",
            requested_at=now_iso(),
            timeout_at=None,
            evidence_ids=(),
        )
    )
    _audit(ctx, run_id, "gate.opened", sid, gid)


def _handoff(ctx: Context, run_id: str, sid: str, brief: str) -> Outcome:
    """Assist mode: a person does the work. Evidence must be recorded before resuming."""
    ctx.store.set_step_status(run_id, sid, "handoff")
    ctx.store.set_run_status(run_id, "gate_waiting")
    _audit(ctx, run_id, "step.handoff", sid, brief)
    return Outcome(Exit.WAITING, run_id, f"{sid} handed to a person (brief: {brief})")


def _check_handoff(ctx: Context, run_id: str, sid: str, step: Step) -> Outcome | None:
    if _state(ctx, run_id).submitted(sid):
        # The person handed the step back: check it. Its evidence is written only if the checks
        # pass (by _complete, after the gate when there is one), never before.
        return _finish_step(ctx, run_id, sid, step)
    missing = [e for e in step.producesEvidence if not ctx.store.has_evidence(run_id, e)]
    if missing:
        ctx.store.set_run_status(run_id, "gate_waiting")
        return Outcome(
            Exit.WAITING,
            run_id,
            f"{sid} is with a person. When the work is done: asac submit {run_id}",
        )
    return _finish_step(ctx, run_id, sid, step)


def submit_step(ctx: Context, run_id: str, by: str) -> Outcome:
    """A person hands back the step they worked on. Records it, then lets the run go on.

    Nothing is written as evidence here: the step's checks decide, then the gate.
    """
    rec = ctx.store.get_run(run_id)  # NotFound surfaces to the caller
    waiting = [s for s, st in ctx.store.list_steps(run_id).items() if st == "handoff"]
    if not waiting:
        raise StateError(f"run '{run_id}' is not waiting for a person (status {rec.status})")
    sid = waiting[0]
    ctx.store.append_audit(run_id, by, "step.submitted", now_iso(), step_id=sid)
    return execute(ctx, run_id)


def _finish_step(ctx: Context, run_id: str, sid: str, step: Step) -> Outcome | None:
    if step.loop is not None and ctx.root is not None:
        turn = _loop_turn(ctx, run_id, sid, step)
        if turn is not None:
            return turn  # the agent gets another turn (or the step failed at the cap)
    if ctx.root is not None:
        blocked = _post_step_hooks(ctx, run_id, sid)
        if blocked is not None:
            if _state(ctx, run_id).submitted(sid):
                # A person submitted it: hand it back to them, with the reason, to fix and submit.
                ctx.store.set_step_status(run_id, sid, "handoff")
                ctx.store.set_run_status(run_id, "gate_waiting")
                _audit(ctx, run_id, "step.handoff", sid, "returned: the checks failed")
            return blocked
    # The hooks passed on this tree: the gate will approve exactly this commit.
    sha = _commit_if_isolated(ctx, run_id, sid)
    if step.gate is not None:
        return _open_gate(ctx, run_id, sid, step.gate, step.producesEvidence, sha)
    _complete(ctx, run_id, sid, step, approved_by=None)
    return None


def _commit_if_isolated(ctx: Context, run_id: str, sid: str) -> str | None:
    """Commit the step in its worktree (ASAC does it). Not isolated: nothing to commit."""
    if ctx.workdir_for is None:
        return None
    work = ctx.workdir_for(run_id)
    if work is None:
        return None
    try:
        sha = commit_step(ctx.root, work, run_id, sid) if ctx.root is not None else None
        if sha is None:
            return None
    except WorkspaceError as exc:
        _audit(ctx, run_id, "commit.failed", sid, str(exc))
        return None
    _audit(ctx, run_id, "step.committed", sid, sha)
    return sha


def _loop_turn(ctx: Context, run_id: str, sid: str, step: Step) -> Outcome | None:
    """One turn of ``step.loop``: run the checks; if one fails, hand the step back with the reason.

    Returns None when every check passes (the step goes on). Each turn is audited. At the cap the
    step fails: a check that never passes never validates the step.
    """
    assert step.loop is not None and ctx.root is not None
    turn = _state(ctx, run_id).loop_turns(sid) + 1
    env = {"ASAC_RUN_ID": run_id, "ASAC_STEP": sid, "ASAC_HOOK_ATTACH": "loop"}
    work = ctx.workdir_for(run_id) if ctx.workdir_for is not None else None
    if work is not None:
        env["ASAC_WORKTREE"] = str(work)
        env["ASAC_ROOT"] = str(ctx.root)
    failures: list[str] = []
    for name in step.loop.until:
        try:
            r = run_hooks_named(ctx.manifest, ctx.root, name, env=env, workdir=work)
        except HookError as exc:
            return _fail(ctx, run_id, sid, f"loop check '{name}': {exc}")
        if not r.passed:
            failures.append(f"{name}: {r.output.strip()[:1500]}")
    if not failures:
        _audit(ctx, run_id, "step.iteration", sid, f"{turn} of {step.loop.max_iterations} passed")
        return None
    reason = "\n".join(failures)
    _audit(ctx, run_id, "step.iteration", sid,
           f"{turn} of {step.loop.max_iterations} failed: {reason[:800]}")  # fmt: skip
    if turn >= step.loop.max_iterations:
        return _fail(ctx, run_id, sid, f"loop cap reached after {turn} turns: {failures[0][:200]}")
    _write_feedback(ctx, run_id, sid, turn, reason)
    ctx.store.set_step_status(run_id, sid, "handoff")
    ctx.store.set_run_status(run_id, "gate_waiting")
    return Outcome(Exit.WAITING, run_id, f"{sid} turn {turn} failed its checks; back to the agent")


def _agent_owes_another_turn(
    ctx: Context, run_id: str, sid: str, step: Step, out: Outcome | None
) -> bool:
    """True when ASAC must launch the tool again for this step.

    Two cases: a loop turn failed its checks, or a human rejected the result with a reason.
    Both only when ASAC launched the tool itself (autorun): a person doing the work hands back
    by themselves. Both are capped, so this never loops forever.
    """
    if out is None or out.code != Exit.WAITING:
        return False
    if ctx.store.get_step_status(run_id, sid) != "handoff":
        return False
    return _state(ctx, run_id).tool_launched(sid)


def _write_feedback(ctx: Context, run_id: str, sid: str, turn: int, reason: str) -> None:
    """The agent's next brief carries the reason its previous turn was rejected."""
    assert ctx.state_dir is not None
    path = ctx.state_dir / "briefs" / run_id / f"{sid}.feedback.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    note = (
        f"\n## Feedback from turn {turn}\n\nThe checks below failed. Fix them, then stop. "
        f"Do not weaken the checks.\n\n```\n{reason}\n```\n"
    )
    with path.open("a", encoding="utf-8") as f:
        f.write(note)


def _post_step_hooks(ctx: Context, run_id: str, sid: str) -> Outcome | None:
    return _run_hooks(ctx, run_id, sid, "post_step")


def _run_hooks(ctx: Context, run_id: str, sid: str, attach: str) -> Outcome | None:
    """Run the hooks attached at ``pre_tool`` (before the agent works) or ``post_step``."""
    assert ctx.root is not None
    env = {"ASAC_RUN_ID": run_id, "ASAC_STEP": sid, "ASAC_HOOK_ATTACH": attach}
    work = ctx.workdir_for(run_id) if ctx.workdir_for is not None else None
    if work is not None:
        env["ASAC_WORKTREE"] = str(work)  # where the agent's output is
        env["ASAC_ROOT"] = str(ctx.root)  # the main checkout: rules, manifest, state
    try:
        results = run_hooks(
            ctx.manifest, ctx.root, attach, env=env, workdir=work, step=ctx.pipeline.steps[sid]
        )
    except HookError as exc:
        return _fail(ctx, run_id, sid, f"hook error: {exc}")
    for r in results:
        shown = r.output.strip()[:2000]
        # First line: "<moment> <hook>", so a reader knows whether it ran before the agent
        # (pre_tool) or after the step (post_step). The hook's output follows.
        detail = f"{attach} {r.name}" + (f"\n{shown}" if shown else "")
        _audit(ctx, run_id, "hook.passed" if r.passed else "hook.failed", sid, detail)
        if not r.passed and r.on_fail == "block":
            return _block(ctx, run_id, sid, f"hook '{r.name}' failed: {r.output}", True)
    return None


def _open_gate(
    ctx: Context, run_id: str, sid: str, gate: Gate, produces: list[str], subject: str | None = None
) -> Outcome:
    at = now_iso()
    gid = gate_id_for(run_id, sid)
    try:
        ctx.store.get_gate(gid)  # resume after a crash: the gate already exists
    except NotFound:
        timeout_at = fmt(clock.now() + parse_duration(gate.timeout)) if gate.timeout else None
        ctx.store.open_gate(
            GateRecord(
                gate_id=gid,
                run_id=run_id,
                step_id=sid,
                type=gate.type,
                role=gate.role,
                status="pending",
                requested_at=at,
                timeout_at=timeout_at,
                evidence_ids=tuple(produces),
                subject=subject,
            )
        )
    ctx.store.set_step_status(run_id, sid, "gate_waiting")
    ctx.store.set_run_status(run_id, "gate_waiting")
    _audit(ctx, run_id, "gate.opened", sid, gid)
    _notify(ctx, run_id, sid, "gate.opened", f"Decision needed: {gid}",
            body=f"Step {sid} of run {run_id} waits for a {gate.type} gate.",
            gate_id=gid, **({"role": gate.role} if gate.role else {}))  # fmt: skip
    return Outcome(Exit.WAITING, run_id, f"waiting for gate {gid}", gates=(gid,))


def _resolve_gate(ctx: Context, run_id: str, sid: str, step: Step) -> Outcome | None:
    gid = gate_id_for(run_id, sid)
    try:
        gate = ctx.store.get_gate(gid)
    except NotFound:
        return _resolve_escalation(ctx, run_id, sid, step)
    if gate.status == "pending":
        if gate.timeout_at and clock.now() > parse_ts(gate.timeout_at):
            ctx.store.decide_gate(gid, "expired", "system", now_iso(), None)
            _audit(ctx, run_id, "gate.expired", sid, gid)
            return _fail(ctx, run_id, sid, f"gate {gid} expired")
        ctx.store.set_run_status(run_id, "gate_waiting")
        return Outcome(Exit.WAITING, run_id, f"waiting for gate {gid}", gates=(gid,))
    if gate.status == "approved":
        ctx.store.set_run_status(run_id, "running")
        _complete(ctx, run_id, sid, step, approved_by=gate.decided_by)
        return None
    if gate.status == "rejected" and _can_relaunch_after_rejection(ctx, run_id, sid, step):
        retry = _retry_after_rejection(ctx, run_id, sid, step, gate)
        if retry is not None:
            return retry
    return _fail(ctx, run_id, sid, f"gate {gid} {gate.status}")


def rejection_cap(step: Step) -> int:
    """Attempts allowed after a human rejection. The loop's cap when the step has one, else 2."""
    return step.loop.max_iterations if step.loop is not None else 2


def _retry_after_rejection(
    ctx: Context, run_id: str, sid: str, step: Step, gate: GateRecord
) -> Outcome | None:
    """A rejection with a reason sends the step back to the agent, up to the cap.

    The reason goes into the step's feedback, so the next launch carries it. Each rejection is
    audited. Past the cap the run fails as before: a human who keeps rejecting cannot loop forever.
    """
    attempts = _state(ctx, run_id).rejection_attempts(sid)
    if attempts >= rejection_cap(step) or ctx.state_dir is None:
        return None
    reason = gate.comment or "no reason given"
    _write_rejection_feedback(ctx, run_id, sid, attempts + 1, reason)
    _audit(ctx, run_id, "rejection.handled", sid,
           f"rejection {attempts + 1} of {rejection_cap(step)}: {reason[:300]}")  # fmt: skip
    ctx.store.reopen_gate(gate.gate_id)
    ctx.store.set_step_status(run_id, sid, "handoff")
    ctx.store.set_run_status(run_id, "gate_waiting")
    return Outcome(Exit.WAITING, run_id, f"{sid} rejected: sent back to the agent with the reason")


def _rejected_gate(ctx: Context, run_id: str, sid: str) -> GateRecord | None:
    """The step's gate, if the reviewer has rejected it (and it has not been reopened)."""
    try:
        gate = ctx.store.get_gate(gate_id_for(run_id, sid))
    except NotFound:
        return None
    return gate if gate.status == "rejected" else None


def _can_relaunch_after_rejection(ctx: Context, run_id: str, sid: str, step: Step) -> bool:
    """ASAC relaunches the agent after a rejection only when it launches the tool itself
    (autorun), and only while the cap allows it. Otherwise the rejection keeps its old meaning:
    the run fails, and the reason stays in the audit."""
    if not (ctx.autorun or step.mode == "delegate"):
        return False
    return _state(ctx, run_id).rejection_attempts(sid) < rejection_cap(step)


def _write_rejection_feedback(
    ctx: Context, run_id: str, sid: str, attempt: int, reason: str
) -> None:
    assert ctx.state_dir is not None
    path = ctx.state_dir / "briefs" / run_id / f"{sid}.feedback.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    note = (
        f"\n## Rejected by the reviewer (attempt {attempt})\n\n"
        f"The reviewer rejected your previous result with this reason. Address it, then stop.\n\n"
        f"```\n{reason}\n```\n"
    )
    with path.open("a", encoding="utf-8") as f:
        f.write(note)


def _resolve_escalation(ctx: Context, run_id: str, sid: str, step: Step) -> Outcome | None:
    """The person answered an escalation: approval lets the step continue, rejection fails it."""
    gid = escalation_gate_id(run_id, sid)
    gate = ctx.store.get_gate(gid)  # NotFound here means the state is corrupt: let it surface
    if gate.status == "pending":
        ctx.store.set_run_status(run_id, "gate_waiting")
        return Outcome(Exit.WAITING, run_id, f"waiting for gate {gid}", gates=(gid,))
    if gate.status == "approved":
        ctx.store.set_run_status(run_id, "running")
        return _finish_step(ctx, run_id, sid, step)
    return _fail(ctx, run_id, sid, f"escalation {gid} {gate.status}")


def reopen(ctx: Context, run_id: str, by: str) -> list[str]:
    """Reopen the rejected gate(s) of a failed run so it can be decided again.

    The rejection stays in the audit. Returns the reopened gate ids.
    """
    rec = ctx.store.get_run(run_id)
    if rec.status != "failed":
        raise StateError(f"run '{run_id}' is {rec.status}; only a failed run can be reopened")
    reopened: list[str] = []
    for g in ctx.store.list_gates("rejected"):
        if g.run_id != run_id:
            continue
        ctx.store.reopen_gate(g.gate_id)
        ctx.store.set_step_status(run_id, g.step_id, "gate_waiting")
        ctx.store.append_audit(run_id, by, "gate.reopened", now_iso(), step_id=g.step_id,
                               detail=g.gate_id)  # fmt: skip
        reopened.append(g.gate_id)
    if not reopened:
        raise StateError(f"run '{run_id}' has no rejected gate to reopen")
    ctx.store.set_run_status(run_id, "gate_waiting")
    return reopened


def decide_gate(
    ctx_store: StateStore,
    gate_id: str,
    status: Literal["approved", "rejected"],
    by: str,
    roles: set[str],
    comment: str | None,
    actor: str = "cli",
) -> GateRecord:
    """Approve or reject a pending gate. Checks the role and the timeout first."""
    gate = ctx_store.get_gate(gate_id)
    at = now_iso()
    if gate.status != "pending":
        raise StateError(f"gate '{gate_id}' is already {gate.status}")
    if gate.timeout_at and clock.now() > parse_ts(gate.timeout_at):
        ctx_store.decide_gate(gate_id, "expired", "system", at, None)
        ctx_store.append_audit(gate.run_id, actor, "gate.expired", at, step_id=gate.step_id)
        raise StateError(f"gate '{gate_id}' has expired")
    if status == "rejected" and not (comment and comment.strip()):
        raise StateError("a rejection needs a comment (the reason is part of the audit)")
    if gate.role and gate.role not in roles:
        raise Forbidden(f"gate '{gate_id}' requires role '{gate.role}'")
    updated = ctx_store.decide_gate(gate_id, status, by, at, comment)
    ctx_store.append_audit(
        gate.run_id, by, f"gate.{status}", at, step_id=gate.step_id, detail=comment or ""
    )
    return updated


__all__ = [
    "submit_step",
    "Context",
    "Exit",
    "Forbidden",
    "NotFound",
    "Outcome",
    "create_run",
    "decide_gate",
    "execute",
    "reopen",
    "gate_id_for",
]
