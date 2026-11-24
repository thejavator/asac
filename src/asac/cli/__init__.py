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

app = typer.Typer(
    help="ASAC: Agentic SDLC as Code (spec v0.4). Version 0.1 supports: init, doctor, validate, "
    "vars, plan, apply, run, submit, approve, gates, status, logs, audit, evidence, learn, "
    "clean, kill.",
    no_args_is_help=True,
)
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
    from asac.loader.load import DuplicateKey, load_manifest

    try:
        return load_manifest(manifest)
    except FileNotFoundError:
        typer.echo(f"error: {manifest} not found", err=True)
        raise typer.Exit(1) from None
    except DuplicateKey as exc:
        typer.echo(f"error {manifest.name}: {exc}", err=True)
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
    # No values file yet: every variable without a default is simply still to be set.
    provided = set(load_vars(vp).user_values()) if vp.exists() else set()
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

TEMPLATES = ("minimal", "feature")
GITIGNORE_ENTRIES = ("asac.vars.yaml", ".asac-state/")

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
    workspace = name or path.resolve().name
    stack = detect_stack(path)
    files = _template_files(template, workspace)
    clash = [rel for rel in files if (path / rel).exists()]
    if clash and not force:
        typer.echo(f"error: {path / clash[0]} exists (use --force)", err=True)
        raise typer.Exit(1)
    for rel, text in files.items():
        target = path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        if target.suffix == ".sh":
            target.chmod(0o755)
    for sub in ("policies", "hooks", "knowledge", "instructions"):
        (path / ".asac" / sub).mkdir(parents=True, exist_ok=True)
    if template != "minimal":  # the empty manifest is the only file `minimal` creates (F66.8)
        _ignore_local_files(path)
    typer.echo(f"created {path / 'asac.yaml'} (stack: {stack}, template: {template})")
    if template == "feature":
        typer.echo("next: cp asac.vars.yaml.example asac.vars.yaml, then asac vars check")
        if stack not in ("python", "generic"):
            typer.echo(
                f"note: the tests-green hook runs python3 -m unittest; edit "
                f".asac/hooks/tests-green.sh for a {stack} project"
            )


def _template_files(template: str, workspace: str) -> dict[str, str]:
    """The files a template creates, as relative path -> text. ``__NAME__`` is the workspace."""
    if template == "minimal":
        return {"asac.yaml": _STARTER.format(name=workspace)}
    root = Path(__file__).resolve().parent.parent / "templates" / template
    return {
        str(f.relative_to(root)): f.read_text(encoding="utf-8").replace("__NAME__", workspace)
        for f in sorted(root.rglob("*"))
        if f.is_file() and f.name != ".DS_Store"
    }


def _ignore_local_files(path: Path) -> None:
    """Keep the local values and the state folder out of git, without touching other lines."""
    target = path / ".gitignore"
    have = target.read_text(encoding="utf-8").splitlines() if target.exists() else []
    missing = [e for e in GITIGNORE_ENTRIES if e not in have]
    if missing:
        text = "\n".join([*have, *missing]) + "\n"
        target.write_text(text, encoding="utf-8")


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


def _report(outcome: Outcome, manifest_path: Path | None = None) -> None:
    typer.echo(f"run {outcome.run_id}: {outcome.message}")
    for g in outcome.gates:
        typer.echo(f"gate {g} is pending. Approve with: asac approve {g}")
    if manifest_path is not None:
        _tell_where_the_work_is(manifest_path, outcome.run_id)


def _tell_where_the_work_is(manifest_path: Path, run_id: str) -> None:
    """When a step waits for a person: the worktree to work in, and how to hand it back."""
    from asac.engine.runtime import recorded_workspace

    try:
        store = store_for_path(manifest_path)
        waiting = "handoff" in store.list_steps(run_id).values()
        work = recorded_workspace(store, run_id) if waiting else None
    except Exception:  # a report must never fail the command it reports on
        return
    if work is None:
        return
    typer.echo(f"work in: {work}\n  cd {work}\nwhen done: asac submit {run_id}")


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
    _report(outcome, manifest_path)
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
    from asac.ports.state import NotFound, StateError

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
    _report(outcome, (ctx.root / "asac.yaml") if ctx.root is not None else None)
    if exit_after:
        raise typer.Exit(int(outcome.code))


@app.command()
def run(
    step: Annotated[str | None, typer.Argument(help="Run only this step.")] = None,
    file: ManifestOpt = Path("asac.yaml"),
    pipeline: PipelineOpt = None,
    harness: HarnessOpt = None,
) -> None:
    """Create a run and execute it (same exit codes as apply). With a step, run only that step."""
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
        commit = f" commit={g.subject[:12]}" if g.subject else ""
        typer.echo(f"{g.gate_id}  {g.status:<9} role={role}{due}{commit}")


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


@app.command()
def submit(
    run_id: Annotated[str, typer.Argument(help="Run whose step you worked on.")],
    file: ManifestOpt = Path("asac.yaml"),
    by: Annotated[str | None, typer.Option("--by", help="Who hands the step back.")] = None,
    harness: HarnessOpt = None,
) -> None:
    """Hand back the step you worked on. Its checks run; its evidence is recorded if they pass."""
    from asac.engine.apply import submit_step
    from asac.engine.runtime import make_context, project_root
    from asac.ports.state import NotFound, StateError

    manifest = _load(file)
    store = store_for_path(file)
    who = by or os.environ.get("USER", "unknown")
    try:
        rec = store.get_run(run_id)
    except NotFound:
        typer.echo(f"error: run '{run_id}' not found", err=True)
        raise typer.Exit(EXIT_ERROR) from None
    ctx = make_context(manifest, rec.pipeline, store, project_root(file), harness)
    try:
        outcome = submit_step(ctx, run_id, who)
    except StateError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(EXIT_ERROR) from None
    _report(outcome, file)
    raise typer.Exit(int(outcome.code))


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


#: audit events whose detail is the point of the line, so the default view prints it
SHOWN_WITH_DETAIL = frozenset({"sandbox.denied", "integrity.violated", "gate.denied"})


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
        line = f"{a.seq:>4} {a.at}  {a.actor:<10} {a.action}  {a.run_id or '-'}"
        if a.action in SHOWN_WITH_DETAIL:  # a reviewer must see what was refused or tampered with
            line += f"  {a.detail.splitlines()[0] if a.detail else ''}"
        typer.echo(line)


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


@app.command(hidden=True)
def portal(
    data: Annotated[
        Path, typer.Option(help="Portal data folder (projects, sessions, admin).")
    ] = Path(".asac-portal"),
    host: Annotated[
        str, typer.Option(help="Bind address. Put a TLS proxy in front.")
    ] = "127.0.0.1",
    port: Annotated[int, typer.Option(help="Listen port.")] = 8080,
    harness: Annotated[str | None, typer.Option(help="Harness used to resume runs.")] = None,
    local: Annotated[
        bool,
        typer.Option(
            "--local",
            help="Developer mode: serve the project of --file on this machine, no sign-in.",
        ),
    ] = False,
    file: ManifestOpt = Path("asac.yaml"),
    project: Annotated[
        list[str] | None,
        typer.Option(
            "--project",
            help="Register a project at startup, as ID=PATH-TO-asac.yaml (repeatable, idempotent).",
        ),
    ] = None,
) -> None:
    """Serve the governance portal. OIDC settings come from ASAC_OIDC_* variables."""
    from asac.portal.app import PortalSettings, create_app
    from asac.portal.oidc import OidcConfig

    env = os.environ
    if local:
        _portal_local(file, host, port, harness)
        return
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
    if project:
        _register_projects(data, project)
    settings = PortalSettings(
        data_dir=data,
        oidc=oidc,
        dev_personas=personas,
        harness=harness,
        secure_cookie=oidc is not None,
    )
    _serve(create_app(settings), host, port)


LOCAL_HOSTS = ("127.0.0.1", "localhost", "::1")


def local_portal_dir(manifest: Path) -> Path:
    """Where the local portal keeps its own data: outside the repository, one folder per project."""
    import hashlib

    root = manifest.resolve().parent
    tag = hashlib.sha256(str(root).encode()).hexdigest()[:10]
    return Path.home() / ".asac" / "portal" / f"{root.name}-{tag}"


def _portal_local(manifest: Path, host: str, port: int, harness: str | None) -> None:
    """The developer's portal: this project, this machine, no sign-in."""
    from asac.adapters.projects_sqlite import SqliteProjectRegistry
    from asac.portal.app import PortalSettings, create_app
    from asac.portal.oidc import Identity
    from asac.ports.projects import Project

    if os.environ.get("ASAC_OIDC_ISSUER"):
        typer.echo("error: --local has no sign-in, so it cannot be combined with OIDC", err=True)
        raise typer.Exit(1)
    if host not in LOCAL_HOSTS:
        typer.echo(
            f"error: --local has no sign-in and must stay on 127.0.0.1 (got {host}); "
            "for a shared portal use OIDC",
            err=True,
        )
        raise typer.Exit(1)
    path = manifest.resolve()
    if not path.is_file():
        typer.echo(f"error: {path} does not exist", err=True)
        raise typer.Exit(1)
    data = local_portal_dir(path)
    data.mkdir(parents=True, exist_ok=True)
    registry = SqliteProjectRegistry(data / "portal-admin.db")
    pid = _project_id(path.parent.name)
    known = {p.id for p in registry.load(include_archived=True).projects}
    if pid not in known:
        registry.create(Project(pid, path.parent.name, path))
    personas = {
        "po": Identity("local-po", "Product owner", frozenset({"product_owner"})),
        "dev": Identity("local-dev", "Developer", frozenset({"developer"})),
        "auditor": Identity("local-auditor", "Auditor", frozenset({"auditor", "manager"})),
        "admin": Identity("local-admin", "Admin", frozenset({"admin"})),
    }
    os.environ["ASAC_ENV"] = "dev"  # this process only: the dev personas need it
    typer.echo(
        f"ASAC portal (local mode): http://{host}:{port}/  project '{pid}' from {path}\n"
        "No sign-in: choose a role on the login page. Reachable from this machine only. "
        "For a shared portal, use OIDC instead.\n"
        f"Portal data: {data}"
    )
    _say_which_state(path)
    settings = PortalSettings(
        data_dir=data, dev_personas=personas, harness=harness, secure_cookie=False,
        shared_state=True,
    )  # fmt: skip
    _serve(create_app(settings), host, port)


def _register_projects(data: Path, specs: list[str]) -> None:
    """``--project ID=PATH``: make sure each project is in the portal database.

    Safe to repeat: a pod that restarts passes the same flags. An existing id is left as it is
    (its name, team and access may have been edited in the portal since).
    """
    from asac.adapters.projects_sqlite import SqliteProjectRegistry
    from asac.ports.projects import PROJECT_ID, Project

    parsed: list[tuple[str, Path]] = []
    for spec in specs:
        pid, sep, raw = spec.partition("=")
        if not sep or not raw or not PROJECT_ID.match(pid):
            typer.echo(
                f"error: --project '{spec}' must be ID=PATH "
                "(id: lower case letters, digits, dashes)",
                err=True,
            )
            raise typer.Exit(1)
        path = Path(raw).resolve()
        if not path.is_file():
            typer.echo(f"error: --project {pid}: {path} does not exist", err=True)
            raise typer.Exit(1)
        parsed.append((pid, path))
    data.mkdir(parents=True, exist_ok=True)
    registry = SqliteProjectRegistry(data / "portal-admin.db")
    known = {p.id for p in registry.load(include_archived=True).projects}
    for pid, path in parsed:
        if pid not in known:
            registry.create(Project(pid, pid, path))
            typer.echo(f"registered project {pid} ({path})")


def _say_which_state(manifest: Path) -> None:
    """Name the state the portal reads and how many runs it holds.

    The CLI and the portal are two processes that must read the same state. When
    ASAC_STATE_DIR differs between their shells they silently read different ones, and the portal
    looks empty. Saying so at startup turns that into something the user can see.
    """
    from asac.adapters import state_dir
    from asac.engine.runtime import store_for

    where = state_dir(manifest.resolve().parent)
    try:
        store = store_for(manifest)
        runs = len(store.list_runs())
        close = getattr(store, "close", None)
        if callable(close):
            close()
    except Exception as exc:  # an unreadable state is worth saying, not worth crashing for
        typer.echo(f"State read: {where} (cannot be read: {exc})")
        return
    typer.echo(f"State read: {where} ({runs} run{'' if runs == 1 else 's'})")
    if runs == 0 and not os.environ.get("ASAC_STATE_DIR"):
        typer.echo(
            "No runs here. If your CLI runs wrote their state somewhere else (ASAC_STATE_DIR was "
            "set in that shell), export the same ASAC_STATE_DIR here and restart: another state "
            "may exist."
        )


def _project_id(name: str) -> str:
    """A folder name as a portal project id (lower case, digits, dashes, starting with a letter)."""
    import re

    pid = re.sub(r"[^a-z0-9-]+", "-", name.lower()).strip("-")[:40] or "project"
    return pid if pid[0].isalpha() else f"p-{pid}"[:41]


project_app = typer.Typer(help="Manage the projects of a portal database.", no_args_is_help=True)
app.add_typer(project_app, name="project", hidden=True)
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


@app.command(hidden=True)
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


@app.command()
def clean(
    run_id: Annotated[str, typer.Argument(help="Run whose worktree to remove.")],
    file: ManifestOpt = Path("asac.yaml"),
    force: Annotated[
        bool, typer.Option("--force", help="Remove it even if the run is not finished.")
    ] = False,
) -> None:
    """Remove a run's worktree. Its branch is kept: that is the work to review and merge."""
    from asac import clock
    from asac.engine.runtime import project_root, recorded_workspace
    from asac.engine.workspace import WorkspaceError, remove_workspace
    from asac.ports.state import NotFound, StateError

    store = store_for_path(file)
    try:
        rec = store.get_run(run_id)
    except NotFound:
        typer.echo(f"error: run '{run_id}' not found", err=True)
        raise typer.Exit(EXIT_ERROR) from None
    try:
        path = recorded_workspace(store, run_id)
    except StateError:
        path = None  # recorded, but already removed: nothing left to clean
    if path is None or not path.exists():
        typer.echo(f"run {run_id}: no worktree to clean")
        return
    if rec.status not in ("completed", "failed", "killed") and not force:
        typer.echo(
            f"error: run {run_id} is still {rec.status}; its worktree is needed to resume "
            "(use --force to remove it anyway)",
            err=True,
        )
        raise typer.Exit(EXIT_ERROR)
    branch = f"asac/{run_id}"
    try:
        remove_workspace(project_root(file), path, branch)
    except WorkspaceError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(EXIT_ERROR) from None
    store.append_audit(run_id, os.environ.get("USER", "cli"), "workspace.removed",
                       clock.now_iso(), detail=str(path))  # fmt: skip
    typer.echo(f"run {run_id}: worktree removed; branch {branch} kept")


@app.command()
def doctor(file: ManifestOpt = Path("asac.yaml")) -> None:
    """Check what a run needs (git, opa, node, srt, claude) and say how to fix what is missing."""
    from asac import doctor as checks

    results = checks.run_checks(file.resolve().parent)
    failed = False
    for c in results:
        mark = "ok  " if c.ok else ("FAIL" if c.required else "warn")
        typer.echo(f"{mark}  {c.name:<15} {c.detail}")
        failed = failed or (not c.ok and c.required)
    if failed:
        raise typer.Exit(EXIT_ERROR)
