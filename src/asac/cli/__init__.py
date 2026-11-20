from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Annotated, Any

import typer
from pydantic import ValidationError

from asac.engine.apply import Context, Outcome
from asac.model import Manifest

app = typer.Typer(help="ASAC: Agentic SDLC as Code (spec v0.4).", no_args_is_help=True)
vars_app = typer.Typer(help="Inspect layer 2 (asac.vars.yaml).", no_args_is_help=True)
app.add_typer(vars_app, name="vars")
evidence_app = typer.Typer(help="Inspect and bootstrap evidence.", no_args_is_help=True)
app.add_typer(evidence_app, name="evidence")

ManifestOpt = Annotated[Path, typer.Option("--file", "-f", help="Path to asac.yaml.")]


@app.callback()
def main() -> None:
    """ASAC command line."""


@app.command()
def version() -> None:
    """Print the implementation and the spec version it targets."""
    from asac import SPEC_VERSION, __version__

    typer.echo(f"asac {__version__} (spec {SPEC_VERSION})")


def _vars_path(manifest: Path, vars_opt: Path | None) -> Path:
    return vars_opt or manifest.parent / "asac.vars.yaml"


def _load(manifest: Path):  # type: ignore[no-untyped-def]
    from asac.loader.load import load_manifest

    try:
        return load_manifest(manifest)
    except FileNotFoundError:
        typer.echo(f"error: {manifest} not found", err=True)
        raise typer.Exit(1) from None
    except ValidationError as e:
        from asac.loader.load import describe_validation_error

        for line in describe_validation_error(e):
            typer.echo(line, err=True)
        raise typer.Exit(1) from None


@app.command()
def validate(
    file: ManifestOpt = Path("asac.yaml"),
    vars_file: Annotated[Path | None, typer.Option("--vars")] = None,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Validate asac.yaml (and asac.vars.yaml if present). Exit 1 on errors."""
    from asac.loader.load import load_vars
    from asac.validate import Severity
    from asac.validate import validate as run

    manifest = _load(file)
    vp = _vars_path(file, vars_file)
    vf = load_vars(vp) if vp.exists() else None
    issues = run(manifest, file.parent, vf)
    if as_json:
        typer.echo(json.dumps([{**i.__dict__, "severity": i.severity.value} for i in issues]))
    else:
        for i in issues:
            typer.echo(f"{i.severity.value} {i.code} {i.path}: {i.message}", err=True)
    errors = [i for i in issues if i.severity is Severity.ERROR]
    if not as_json:
        typer.echo(f"{len(errors)} error(s), {len(issues) - len(errors)} warning(s)")
    raise typer.Exit(1 if errors else 0)


def _var_report(file: Path, vars_file: Path | None) -> tuple[list[str], list[str]]:
    from asac.loader.load import load_vars

    manifest = _load(file)
    vp = _vars_path(file, vars_file)
    if not vp.exists():
        typer.echo(f"error: {vp} not found", err=True)
        raise typer.Exit(1)
    provided = set(load_vars(vp).user_values())
    declared = {k for k, v in manifest.variables.items() if v.default is None}
    return sorted(declared - provided), sorted(provided - set(manifest.variables))


@vars_app.command("check")
def vars_check(
    file: ManifestOpt = Path("asac.yaml"),
    vars_file: Annotated[Path | None, typer.Option("--vars")] = None,
) -> None:
    """Fail if a declared variable without default has no value."""
    missing, _ = _var_report(file, vars_file)
    for k in missing:
        typer.echo(f"missing: {k}", err=True)
    raise typer.Exit(1 if missing else 0)


@vars_app.command("diff")
def vars_diff(
    file: ManifestOpt = Path("asac.yaml"),
    vars_file: Annotated[Path | None, typer.Option("--vars")] = None,
) -> None:
    """Show missing and unused variables (reserved keys are never unused)."""
    missing, unused = _var_report(file, vars_file)
    for k in missing:
        typer.echo(f"missing: {k}")
    for k in unused:
        typer.echo(f"unused: {k}")
    raise typer.Exit(1 if missing else 0)


_STARTER = """asac:
  spec: "0.4"
  workspace: {name}

variables: {{}}
providers: {{}}
capabilities: {{}}
evidenceTypes: {{}}
skills: {{}}
agents: {{}}
pipelines: {{}}
"""

_FEATURE = """asac:
  spec: "0.4"
  workspace: {name}

variables:
  llm_api_key: {{ type: string, sensitive: true }}
  dev_harness: {{ type: harness }}

providers:
  llm:
    source: asac/claude
    version: "~> 1.0"
    config: {{ api_key: var.llm_api_key }}

capabilities:
  implementation:
    description: Produce working code from a specification
    evidence: [tests_green]

evidenceTypes:
  tests_green: {{ description: All required tests pass }}

skills:
  impl:
    ref: registry.example.dev/{stack}/implementation@1.0.0
    fulfils: implementation

agents:
  dev: {{ skill: impl, provider: llm, harness: var.dev_harness }}

pipelines:
  feature:
    steps:
      development:
        capability: implementation
        agent: dev
        mode: assist
        producesEvidence: [tests_green]
"""

TEMPLATES = {"minimal": _STARTER, "feature": _FEATURE}

STACK_MARKERS = {
    "pom.xml": "java",
    "build.gradle": "java",
    "package.json": "node",
    "pyproject.toml": "python",
    "go.mod": "go",
}


def detect_stack(path: Path) -> str:
    for marker, stack in STACK_MARKERS.items():
        if (path / marker).exists():
            return stack
    return "generic"


@app.command()
def init(
    path: Annotated[Path, typer.Argument()] = Path("."),
    name: Annotated[str | None, typer.Option("--name")] = None,
    template: Annotated[str, typer.Option("--template")] = "minimal",
    force: Annotated[bool, typer.Option("--force")] = False,
) -> None:
    """Create asac.yaml and the .asac/ layout, detecting the project stack."""
    if template not in TEMPLATES:
        typer.echo(f"error: unknown template '{template}' ({', '.join(TEMPLATES)})", err=True)
        raise typer.Exit(1)
    path.mkdir(parents=True, exist_ok=True)
    target = path / "asac.yaml"
    if target.exists() and not force:
        typer.echo(f"error: {target} exists (use --force)", err=True)
        raise typer.Exit(1)
    stack = detect_stack(path)
    text = TEMPLATES[template].format(name=name or path.resolve().name, stack=stack)
    target.write_text(text, encoding="utf-8")
    for sub in ("policies", "hooks", "knowledge", "instructions"):
        (path / ".asac" / sub).mkdir(parents=True, exist_ok=True)
    typer.echo(f"created {target} (stack: {stack}, template: {template})")


# --- execution (M2): plan, apply, run, status, gates, approve, evidence, logs, audit ---

EXIT_OK, EXIT_ERROR, EXIT_WAITING, EXIT_BLOCKED = 0, 1, 2, 3
HarnessOpt = Annotated[
    str | None,
    typer.Option("--harness", help="Override every agent's harness (e.g. 'fake')."),
]
PipelineOpt = Annotated[str | None, typer.Option("--pipeline", "-p", help="Pipeline name.")]


def _ctx_or_exit(manifest_path: Path, pipeline: str | None, harness: str | None = None):  # type: ignore[no-untyped-def]
    from asac.adapters import harness_available
    from asac.engine.runtime import make_context, project_root, store_for

    manifest = _load(manifest_path)
    if pipeline is None:
        if len(manifest.pipelines) != 1:
            names = ", ".join(manifest.pipelines) or "none"
            typer.echo(f"error: choose a pipeline with --pipeline ({names})", err=True)
            raise typer.Exit(EXIT_ERROR)
        pipeline = next(iter(manifest.pipelines))
    if pipeline not in manifest.pipelines:
        typer.echo(f"error: unknown pipeline '{pipeline}'", err=True)
        raise typer.Exit(EXIT_ERROR)
    if harness is not None and not harness_available(harness):
        typer.echo(f"error: harness '{harness}' has no adapter in this build", err=True)
        raise typer.Exit(EXIT_ERROR)
    store = store_for(manifest_path)
    root = project_root(manifest_path)
    return make_context(manifest, pipeline, store, root, harness), pipeline


@app.command()
def plan(
    file: ManifestOpt = Path("asac.yaml"),
    pipeline: PipelineOpt = None,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Show the step order, gates and estimated cost. Changes nothing."""
    from asac.engine.plan import build_plan, render_plan

    manifest = _load(file)
    name = _pick_pipeline(manifest, pipeline)
    p = build_plan(manifest, name)
    if as_json:
        typer.echo(
            json.dumps(
                {
                    "pipeline": p.pipeline,
                    "steps": [
                        {
                            "id": s.id,
                            "level": s.level,
                            "capability": s.capability,
                            "agent": s.agent,
                            "mode": s.mode,
                            "gate": s.gate,
                            "requires": list(s.requires),
                            "produces": list(s.produces),
                        }
                        for s in p.steps
                    ],
                    "estimated_tokens": p.estimated_tokens,
                    "budget_tokens": p.budget_tokens,
                },
                indent=2,
            )
        )
    else:
        for line in render_plan(p):
            typer.echo(line)
    if p.over_budget:
        raise typer.Exit(EXIT_BLOCKED)


def _pick_pipeline(manifest: Manifest, pipeline: str | None) -> str:
    if pipeline is None:
        if len(manifest.pipelines) != 1:
            typer.echo("error: choose a pipeline with --pipeline", err=True)
            raise typer.Exit(EXIT_ERROR)
        return next(iter(manifest.pipelines))
    if pipeline not in manifest.pipelines:
        typer.echo(f"error: unknown pipeline '{pipeline}'", err=True)
        raise typer.Exit(EXIT_ERROR)
    return pipeline


def _report(outcome: Outcome) -> None:
    typer.echo(f"run {outcome.run_id}: {outcome.message}")
    for g in outcome.gates:
        typer.echo(f"gate {g} is pending. Approve with: asac approve {g}")


def _run_engine(
    manifest_path: Path,
    pipeline: str | None,
    run_id: str | None,
    harness: str | None,
    only: str | None = None,
) -> None:
    from asac.engine.apply import create_run, execute
    from asac.ports.state import StateError

    ctx, name = _ctx_or_exit(manifest_path, pipeline, harness)
    rid = run_id or f"run_{name}_{ctx.store.list_runs().__len__() + 1:04d}"
    try:
        create_run(ctx, rid)
        outcome = execute(ctx, rid, only=only)
    except StateError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(EXIT_ERROR) from None
    _report(outcome)
    raise typer.Exit(int(outcome.code))


@app.command()
def apply(
    file: ManifestOpt = Path("asac.yaml"),
    pipeline: PipelineOpt = None,
    resume: Annotated[str | None, typer.Option("--resume", help="Run id to continue.")] = None,
    run_id: Annotated[str | None, typer.Option("--run-id", help="Id for a new run.")] = None,
    harness: HarnessOpt = None,
    reopen: Annotated[
        bool, typer.Option("--reopen", help="With --resume: reopen the rejected gate first.")
    ] = False,
    watch: Annotated[
        bool,
        typer.Option("--watch", help="Stay in the foreground and continue after each decision."),
    ] = False,
    poll: Annotated[
        float, typer.Option("--poll", help="Seconds between checks with --watch.")
    ] = 2.0,
) -> None:
    """Execute a pipeline. Exits 2 at a gate (never waits unless --watch)."""
    if watch:
        _watch(file, pipeline, resume, run_id, harness, reopen, poll)
        return
    if reopen and resume is None:
        typer.echo("error: --reopen needs --resume <run-id>", err=True)
        raise typer.Exit(EXIT_ERROR)
    if resume is not None:
        _resume(file, resume, harness, reopen)
        return
    _run_engine(file, pipeline, run_id, harness)


def _watch(
    manifest_path: Path,
    pipeline: str | None,
    resume: str | None,
    run_id: str | None,
    harness: str | None,
    reopen: bool,
    poll: float,
) -> None:
    """Run, then keep continuing each time a gate is decided or evidence is recorded."""
    import time

    from asac.engine.apply import create_run, execute
    from asac.engine.runtime import make_context, project_root, store_for
    from asac.ports.state import StateError

    if resume is None:
        ctx, name = _ctx_or_exit(manifest_path, pipeline, harness)
        rid = run_id or f"run_{name}_{len(ctx.store.list_runs()) + 1:04d}"
        try:
            create_run(ctx, rid)
        except StateError as exc:
            typer.echo(f"error: {exc}", err=True)
            raise typer.Exit(EXIT_ERROR) from None
    else:
        rid = resume
        if reopen:
            _resume(manifest_path, rid, harness, True, run=False)
    store = store_for(manifest_path)
    manifest = _load(manifest_path)
    last = ""
    try:
        while True:
            try:
                rec = store.get_run(rid)
            except Exception:
                typer.echo(f"error: run '{rid}' not found", err=True)
                raise typer.Exit(EXIT_ERROR) from None
            ctx = make_context(manifest, rec.pipeline, store, project_root(manifest_path), harness)
            try:
                outcome = execute(ctx, rid)
            except StateError as exc:
                typer.echo(f"error: {exc}", err=True)
                raise typer.Exit(EXIT_ERROR) from None
            text = f"run {outcome.run_id}: {outcome.message}"
            if text != last:
                _report(outcome)
                last = text
            if int(outcome.code) != EXIT_WAITING:
                raise typer.Exit(int(outcome.code))
            time.sleep(poll)
    except KeyboardInterrupt:
        typer.echo("stopped watching; the run keeps its state (asac apply --resume).")
        raise typer.Exit(EXIT_WAITING) from None


def _auto_resume(manifest_path: Path, run_id: str, harness: str | None) -> None:
    """After a human decision, continue the run unless it is finished or broken."""
    store = store_for_path(manifest_path)
    try:
        status = store.get_run(run_id).status
    except Exception:
        return
    if status in ("running", "gate_waiting"):
        _resume(manifest_path, run_id, harness, exit_after=False)


def _resume(
    manifest_path: Path,
    run_id: str,
    harness: str | None,
    reopen: bool = False,
    run: bool = True,
    exit_after: bool = True,
) -> None:
    from asac.ports.state import NotFound

    manifest = _load(manifest_path)
    from asac.engine.runtime import make_context, project_root, store_for

    store = store_for(manifest_path)
    try:
        rec = store.get_run(run_id)
    except NotFound:
        typer.echo(f"error: run '{run_id}' not found", err=True)
        raise typer.Exit(EXIT_ERROR) from None
    ctx = make_context(manifest, rec.pipeline, store, project_root(manifest_path), harness)
    if reopen:
        from asac.engine.apply import reopen as reopen_run
        from asac.ports.state import StateError

        try:
            gates = reopen_run(ctx, run_id, os.environ.get("USER", "unknown"))
        except StateError as exc:
            typer.echo(f"error: {exc}", err=True)
            raise typer.Exit(EXIT_ERROR) from None
        typer.echo(f"reopened: {', '.join(gates)}")
    if run:
        _run_engine_with(ctx, run_id, exit_after=exit_after)


def _run_engine_with(ctx: Context, run_id: str, *, exit_after: bool = True) -> None:
    from asac.engine.apply import execute
    from asac.ports.state import StateError

    try:
        outcome = execute(ctx, run_id)
    except StateError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(EXIT_ERROR) from None
    _report(outcome)
    if exit_after:
        raise typer.Exit(int(outcome.code))


@app.command()
def run(
    step: Annotated[str | None, typer.Argument(help="Run only this step.")] = None,
    file: ManifestOpt = Path("asac.yaml"),
    pipeline: PipelineOpt = None,
    harness: HarnessOpt = None,
) -> None:
    """Plan and apply in one step (same exit codes as apply). With a step, run only that step."""
    _run_engine(file, pipeline, None, harness, only=step)


@app.command()
def status(
    file: ManifestOpt = Path("asac.yaml"),
    run_id: Annotated[str | None, typer.Option("--run-id")] = None,
) -> None:
    """Show runs, or the steps of one run."""
    from asac.ports.state import NotFound

    store = store_for_path(file)
    if run_id is None:
        runs = store.list_runs()
        if not runs:
            typer.echo("no runs")
        for r in runs:
            typer.echo(f"{r.run_id}  {r.pipeline:<12} {r.status}")
        return
    try:
        rec = store.get_run(run_id)
    except NotFound:
        typer.echo(f"error: run '{run_id}' not found", err=True)
        raise typer.Exit(EXIT_ERROR) from None
    typer.echo(f"{rec.run_id}  {rec.pipeline}  {rec.status}")
    for sid, st in store.list_steps(run_id).items():
        typer.echo(f"  {sid:<14} {st}")


def store_for_path(file: Path):  # type: ignore[no-untyped-def]
    from asac.engine.runtime import store_for

    return store_for(file)


@app.command()
def gates(
    file: ManifestOpt = Path("asac.yaml"),
    status_filter: Annotated[str | None, typer.Option("--status")] = None,
) -> None:
    """List gates, pending ones first."""
    store = store_for_path(file)
    for g in store.list_gates(status_filter):
        role = g.role or "-"
        due = f" due {g.timeout_at}" if g.timeout_at else ""
        typer.echo(f"{g.gate_id}  {g.status:<9} role={role}{due}")


@app.command()
def approve(
    gate_id: Annotated[str, typer.Argument()],
    file: ManifestOpt = Path("asac.yaml"),
    role: Annotated[list[str], typer.Option("--role", help="Roles held by the approver.")] = [],  # noqa: B006
    by: Annotated[str | None, typer.Option("--by")] = None,
    comment: Annotated[str | None, typer.Option("--comment")] = None,
    reject: Annotated[bool, typer.Option("--reject")] = False,
    harness: HarnessOpt = None,
    no_resume: Annotated[
        bool, typer.Option("--no-resume", help="Only record the decision.")
    ] = False,
) -> None:
    """Approve (or reject) a pending gate, then continue the run (unless --no-resume)."""
    from asac.engine.apply import Forbidden, decide_gate
    from asac.ports.state import GateError, NotFound, StateError

    store = store_for_path(file)
    who = by or os.environ.get("USER", "unknown")
    try:
        g = decide_gate(
            store, gate_id, "rejected" if reject else "approved", who, set(role), comment
        )
    except Forbidden as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(EXIT_BLOCKED) from None
    except (NotFound, GateError, StateError) as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(EXIT_ERROR) from None
    typer.echo(f"gate {g.gate_id} {g.status} by {g.decided_by}")
    if no_resume:
        typer.echo(f"continue with: asac apply --resume {g.run_id}")
    elif g.status == "approved":
        _auto_resume(file, g.run_id, harness)


@evidence_app.command("show")
def evidence_show(
    run_id: Annotated[str, typer.Argument()],
    file: ManifestOpt = Path("asac.yaml"),
) -> None:
    """List the evidence recorded for a run."""
    store = store_for_path(file)
    for e in store.list_evidence(run_id):
        flags = []
        if e.bootstrapped:
            flags.append("bootstrapped")
        if e.approved_by:
            flags.append(f"approved_by={e.approved_by}")
        extra = f"  [{', '.join(flags)}]" if flags else ""
        typer.echo(f"{e.evidence_id}  by {e.produced_by}  at {e.at}{extra}")


@evidence_app.command("verify")
def evidence_verify(
    run_id: Annotated[str, typer.Argument()],
    file: ManifestOpt = Path("asac.yaml"),
) -> None:
    """Check that every requirement of the run's completed steps is satisfied."""
    manifest = _load(file)
    store = store_for_path(file)
    try:
        rec = store.get_run(run_id)
    except Exception:
        typer.echo(f"error: run '{run_id}' not found", err=True)
        raise typer.Exit(EXIT_ERROR) from None
    pipe = manifest.pipelines[rec.pipeline]
    steps = store.list_steps(run_id)
    problems = []
    for sid, step in pipe.steps.items():
        if steps.get(sid) != "completed":
            continue
        for ev in step.requiresEvidence:
            if not store.has_evidence(run_id, ev):
                problems.append(f"{sid} requires {ev}")
    if problems:
        for p in problems:
            typer.echo(f"missing: {p}", err=True)
        raise typer.Exit(EXIT_ERROR)
    typer.echo("evidence ok")


@evidence_app.command("bootstrap")
def evidence_bootstrap(
    run_id: Annotated[str, typer.Argument()],
    evidence: Annotated[str, typer.Option("--evidence", help="Evidence id to record.")],
    file: ManifestOpt = Path("asac.yaml"),
    by: Annotated[str | None, typer.Option("--by")] = None,
    harness: HarnessOpt = None,
    no_resume: Annotated[
        bool, typer.Option("--no-resume", help="Only record the evidence.")
    ] = False,
) -> None:
    """Record evidence produced outside ASAC (marked bootstrapped, never agent-produced)."""
    from asac import clock
    from asac.ports.state import EvidenceExists, NotFound

    store = store_for_path(file)
    who = by or os.environ.get("USER", "unknown")
    try:
        store.add_evidence(
            run_id,
            evidence,
            produced_by="bootstrap",
            at=clock.now_iso(),
            approved_by=who,
            bootstrapped=True,
        )
    except EvidenceExists as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(EXIT_ERROR) from None
    except NotFound as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(EXIT_ERROR) from None
    store.append_audit(run_id, who, "evidence.bootstrapped", clock.now_iso(), detail=evidence)
    typer.echo(f"recorded {evidence} (bootstrapped by {who})")
    if not no_resume:
        _auto_resume(file, run_id, harness)


@app.command()
def logs(
    run_id: Annotated[str, typer.Argument()],
    file: ManifestOpt = Path("asac.yaml"),
    as_json: Annotated[bool, typer.Option("--json", help="Emit OTel-shaped spans.")] = False,
) -> None:
    """Show the audit trail of a run, in order."""
    store = store_for_path(file)
    records = store.audit(run_id)
    if as_json:
        # One OpenTelemetry-shaped span per audit record (offline; export is up to the user).
        trace = hashlib.sha256(run_id.encode()).hexdigest()[:32]  # stable across processes
        typer.echo(
            json.dumps(
                [
                    {
                        "trace_id": trace,
                        "span_id": f"{a.seq:016x}",
                        "name": a.action,
                        "start_time": a.at,
                        "attributes": {
                            "asac.run_id": run_id,
                            "asac.step_id": a.step_id or "",
                            "asac.actor": a.actor,
                            "asac.detail": a.detail,
                        },
                    }
                    for a in records
                ],
                indent=2,
            )
        )
        return
    for a in records:
        step = f" {a.step_id}" if a.step_id else ""
        detail = f"  {a.detail}" if a.detail else ""
        typer.echo(f"{a.at}  {a.actor:<10} {a.action}{step}{detail}")


@app.command()
def audit(
    file: ManifestOpt = Path("asac.yaml"),
    run_id: Annotated[str | None, typer.Option("--run-id")] = None,
    fmt: Annotated[str, typer.Option("--format")] = "text",
) -> None:
    """Show the audit log, as text or CSV."""
    import csv
    import io

    records = store_for_path(file).audit(run_id)
    if fmt == "csv":
        buf = io.StringIO()
        writer = csv.writer(buf, lineterminator="\n")
        writer.writerow(["seq", "at", "run_id", "step_id", "actor", "action", "detail"])
        for a in records:
            writer.writerow(
                [a.seq, a.at, a.run_id or "", a.step_id or "", a.actor, a.action, a.detail]
            )
        typer.echo(buf.getvalue(), nl=False)
        return
    if fmt != "text":
        typer.echo(f"error: unknown format '{fmt}'", err=True)
        raise typer.Exit(EXIT_ERROR)
    for a in records:
        typer.echo(f"{a.seq:>4} {a.at}  {a.actor:<10} {a.action}  {a.run_id or '-'}")


@app.command()
def kill(
    run_id: Annotated[str, typer.Argument()],
    file: ManifestOpt = Path("asac.yaml"),
    by: Annotated[str | None, typer.Option("--by")] = None,
    reason: Annotated[str, typer.Option("--reason")] = "",
) -> None:
    """Stop a run for good. The engine checks this before every step; it cannot be resumed."""
    from asac import clock
    from asac.ports.state import NotFound

    store = store_for_path(file)
    who = by or os.environ.get("USER", "unknown")
    try:
        rec = store.get_run(run_id)
    except NotFound:
        typer.echo(f"error: run '{run_id}' not found", err=True)
        raise typer.Exit(EXIT_ERROR) from None
    if rec.status in ("completed", "killed"):
        typer.echo(f"error: run '{run_id}' is already {rec.status}", err=True)
        raise typer.Exit(EXIT_ERROR)
    store.set_run_status(run_id, "killed")
    store.append_audit(run_id, who, "run.killed", clock.now_iso(), detail=reason)
    typer.echo(f"run {run_id} killed")


@app.command()
def learn(
    run_id: Annotated[str, typer.Argument()],
    file: ManifestOpt = Path("asac.yaml"),
) -> None:
    """Write a proposal from a run's failures and blocks. Never applied automatically."""
    from asac import clock
    from asac.engine.runtime import project_root
    from asac.ports.state import NotFound

    store = store_for_path(file)
    try:
        rec = store.get_run(run_id)
    except NotFound:
        typer.echo(f"error: run '{run_id}' not found", err=True)
        raise typer.Exit(EXIT_ERROR) from None
    findings = [
        a
        for a in store.audit(run_id)
        if a.action in ("step.failed", "step.blocked", "step.escalated", "hook.failed")
    ]
    lines = [
        f"# Proposal from run {run_id}",
        "",
        f"Pipeline: {rec.pipeline}. Status: {rec.status}. Generated {clock.now_iso()}.",
        "",
        "> A proposal only. Review it and edit `asac.yaml`, instructions or policies by hand;",
        "> ASAC never applies it.",
        "",
        "## Observations",
        "",
    ]
    lines += [f"- `{a.action}` at `{a.step_id or '-'}`: {a.detail}" for a in findings] or [
        "- Nothing to learn: no failure, block or escalation was recorded."
    ]
    out_dir = project_root(file) / ".asac" / "proposals"
    out_dir.mkdir(parents=True, exist_ok=True)
    from asac.adapters.base import safe_name

    target = out_dir / f"{safe_name(run_id)}.md"
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    store.append_audit(run_id, "cli", "proposal.written", clock.now_iso(), detail=str(target.name))
    typer.echo(f"proposal written to {target}")


def _serve(application: object, host: str, port: int) -> None:
    import uvicorn

    uvicorn.run(application, host=host, port=port, log_level="info")  # type: ignore[arg-type]


@app.command()
def portal(
    data: Annotated[
        Path, typer.Option(help="Portal data folder (projects, sessions, admin).")
    ] = Path(".asac-portal"),
    host: Annotated[
        str, typer.Option(help="Bind address. Put a TLS proxy in front.")
    ] = "127.0.0.1",
    port: Annotated[int, typer.Option(help="Listen port.")] = 8080,
    harness: Annotated[str | None, typer.Option(help="Harness used to resume runs.")] = None,
) -> None:
    """Serve the governance portal. OIDC settings come from ASAC_OIDC_* variables."""
    from asac.portal.app import PortalSettings, create_app
    from asac.portal.oidc import OidcConfig

    env = os.environ
    oidc = None
    if env.get("ASAC_OIDC_ISSUER"):
        try:
            oidc = OidcConfig(
                issuer=env["ASAC_OIDC_ISSUER"],
                client_id=env["ASAC_OIDC_CLIENT_ID"],
                client_secret=env.get("ASAC_OIDC_CLIENT_SECRET"),
                redirect_uri=env["ASAC_OIDC_REDIRECT_URI"],
                roles_claim=env.get("ASAC_OIDC_ROLES_CLAIM", "roles"),
            )
        except KeyError as exc:
            typer.echo(f"error: missing environment variable {exc.args[0]}", err=True)
            raise typer.Exit(1) from None
    elif env.get("ASAC_ENV") != "dev":
        typer.echo("error: set ASAC_OIDC_ISSUER (or ASAC_ENV=dev for local use)", err=True)
        raise typer.Exit(1)
    personas = None
    if oidc is None:  # ASAC_ENV=dev only: three local personas, no SSO
        from asac.portal.oidc import Identity

        personas = {
            "po": Identity("dev-po", "Dev PO", frozenset({"product_owner"})),
            "auditor": Identity("dev-auditor", "Dev Auditor", frozenset({"auditor", "manager"})),
            "dev": Identity("dev-dev", "Dev Developer", frozenset({"developer"})),
            "admin": Identity("dev-admin", "Dev Admin", frozenset({"admin"})),
        }
    settings = PortalSettings(
        data_dir=data,
        oidc=oidc,
        dev_personas=personas,
        harness=harness,
        secure_cookie=oidc is not None,
    )
    _serve(create_app(settings), host, port)


project_app = typer.Typer(help="Manage the projects of a portal database.", no_args_is_help=True)
app.add_typer(project_app, name="project")
DataOpt = Annotated[Path, typer.Option(help="Portal data folder (same as `asac portal --data`).")]


def _registry(data: Path) -> Any:
    from asac.adapters.projects_sqlite import SqliteProjectRegistry

    data.mkdir(parents=True, exist_ok=True)
    return SqliteProjectRegistry(data / "portal-admin.db")


@project_app.command("add")
def project_add(
    project_id: Annotated[str, typer.Argument(help="Lower case letters, digits, dashes.")],
    manifest: Annotated[Path, typer.Argument(help="Path of the project's asac.yaml.")],
    name: Annotated[str | None, typer.Option(help="Display name (default: the id).")] = None,
    team: Annotated[str | None, typer.Option()] = None,
    repo: Annotated[str | None, typer.Option(help="Repository URL.")] = None,
    access: Annotated[
        list[str] | None, typer.Option(help="Group that can see it (repeatable).")
    ] = None,
    data: DataOpt = Path(".asac-portal"),
) -> None:
    """Create a project without the web interface (for the first one, or scripts)."""
    from asac.ports.projects import PROJECT_ID, Project, ProjectError

    path = manifest.resolve()
    if not PROJECT_ID.match(project_id):
        typer.echo("error: the id must be lower case letters, digits and dashes", err=True)
        raise typer.Exit(1)
    if not path.is_file():
        typer.echo(f"error: {path} does not exist", err=True)
        raise typer.Exit(1)
    try:
        _registry(data).create(
            Project(project_id, name or project_id, path, team, repo, frozenset(access or []))
        )
    except ProjectError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from None
    typer.echo(f"project {project_id} created")


@project_app.command("list")
def project_list(
    data: DataOpt = Path(".asac-portal"),
    archived: Annotated[bool, typer.Option(help="Include archived projects.")] = False,
) -> None:
    """List the projects."""
    for p in _registry(data).load(include_archived=archived).projects:
        typer.echo(f"{p.id}\t{p.name}\t{p.manifest}\t{'archived' if p.archived else 'active'}")


@project_app.command("archive")
def project_archive(
    project_id: Annotated[str, typer.Argument()],
    restore: Annotated[bool, typer.Option(help="Restore instead of archive.")] = False,
    data: DataOpt = Path(".asac-portal"),
) -> None:
    """Archive a project (or restore it with --restore)."""
    from asac.ports.projects import ProjectError

    try:
        _registry(data).set_archived(project_id, not restore)
    except ProjectError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from None
    typer.echo(f"project {project_id} {'restored' if restore else 'archived'}")


@app.command()
def daemon(
    file: ManifestOpt = Path("asac.yaml"),
    host: Annotated[str, typer.Option(help="Bind address.")] = "127.0.0.1",
    port: Annotated[int, typer.Option(help="Listen port.")] = 8090,
    harness: Annotated[str | None, typer.Option(help="Harness for started runs.")] = None,
) -> None:
    """Serve the webhook receiver (POST /webhooks/jira, HMAC via ASAC_WEBHOOK_SECRET)."""
    from asac.daemon.app import create_app

    if not os.environ.get("ASAC_WEBHOOK_SECRET"):
        typer.echo("error: ASAC_WEBHOOK_SECRET is not set", err=True)
        raise typer.Exit(1)
    _serve(create_app(file, harness), host, port)
