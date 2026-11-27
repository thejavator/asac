"""JSON API ``/api/v1`` used by the SPA. Same sessions, CSRF and engine checks as the pages.

Errors are RFC 9457 ``application/problem+json``. Lists use opaque cursors. The OpenAPI
document is served at ``/api/v1/openapi.json`` and feeds the generated TypeScript client.
"""

from __future__ import annotations

import base64
import binascii
import csv
import io
import secrets
from collections.abc import Callable
from contextlib import AbstractContextManager, suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yaml
from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from asac.engine.apply import Forbidden, decide_gate
from asac.engine.pipeline_edit import (
    DraftConflict,
    has_errors,
    propose,
    refresh,
    unified_diff,
    validate_text,
)
from asac.engine.plan import build_plan, topo_order
from asac.engine.run_state import RunState
from asac.engine.runtime import recorded_workspace
from asac.loader.load import load_manifest
from asac.model import Manifest
from asac.portal.decision import changed_files, checks_from_audit, started_at, urgency
from asac.portal.overview import figures_for, unavailable
from asac.ports.admin import PROJECT_ROLES, AdminStore, Mapping
from asac.ports.artifacts import ArtifactError, ArtifactStore
from asac.ports.drafts import Draft, DraftStore
from asac.ports.forge import Forge, ForgeError, Unsupported
from asac.ports.forge import NotFound as ForgeNotFound
from asac.ports.projects import PROJECT_ID, Directory, Project, ProjectError, ProjectRegistry
from asac.ports.state import GateError, NotFound, StateError, StateStore
from asac.ports.tracker import Tracker, TrackerError
from asac.ports.vars import VarsError, VarsStore
from asac.ports.wiki import Wiki, WikiError

PROBLEM = "application/problem+json"
ORG_AUDIT_ROLES = frozenset({"auditor", "manager"})
VARS_WRITERS = frozenset({"owner", "admin"})
PIPELINE_EDITORS = frozenset({"owner", "developer", "product_owner", "admin"})
RUN_STARTERS = PIPELINE_EDITORS
PIPELINE_FILE = "asac.yaml"


# --- schemas ----------------------------------------------------------------------------


class Problem(BaseModel):
    type: str = "about:blank"
    title: str
    status: int
    detail: str | None = None


class Persona(BaseModel):
    id: str
    name: str
    roles: list[str]


class LoginOptions(BaseModel):
    mode: Literal["oidc", "dev"]
    personas: list[Persona] = []
    organization: str | None = None


class Me(BaseModel):
    sub: str
    name: str
    roles: list[str]
    csrf: str
    organization: str


class ProjectOut(BaseModel):
    id: str
    name: str
    team: str | None
    repo: str | None
    roles: list[str]
    active_runs: int
    problem_runs: int
    pending_gates: int
    my_pending_gates: int
    error: bool = False


class ProjectFiguresOut(BaseModel):
    """One project's figures. Every number is declared: it comes from the project's own runs."""

    project_id: str
    name: str
    team: str | None
    runs: int
    active: int
    completed: int
    problems: int
    pending_gates: int
    cost_usd: float
    tokens: int
    cost_unknown_runs: int
    integrity_violations: int
    sandbox_denials: int
    hooks_passed: int
    hooks_failed: int
    check_pass_rate: float | None
    unavailable: bool


class OverviewOut(BaseModel):
    """The organisation view. ``assurance`` says how much a number can be trusted."""

    assurance: Literal["declared", "verified"]
    projects: list[ProjectFiguresOut]
    totals: dict[str, float]


class RunOut(BaseModel):
    run_id: str
    pipeline: str
    status: str
    created_at: str
    steps: list[StepOut]


class StepOut(BaseModel):
    id: str
    status: str


class RunPage(BaseModel):
    items: list[RunOut]
    next_cursor: str | None


class EvidenceOut(BaseModel):
    evidence_id: str
    produced_by: str
    approved_by: str | None
    bootstrapped: bool
    at: str


class GateOut(BaseModel):
    gate_id: str
    run_id: str
    step_id: str
    type: str
    role: str | None
    status: str
    requested_at: str
    timeout_at: str | None
    decided_by: str | None
    decided_at: str | None
    comment: str | None
    can_decide: bool


class CheckOut(BaseModel):
    kind: str  # "hook"
    name: str
    moment: str  # "pre_tool" | "post_step"; empty for an audit that did not record it
    passed: bool
    output: str


class ChangedFileOut(BaseModel):
    path: str
    change: str  # added | modified | deleted | renamed
    mounted: bool = False  # mounted by ASAC for the tool, not written by the agent


class PendingDecision(GateOut):
    project_id: str
    project_name: str
    pipeline: str = ""
    run_started_at: str | None = None
    cost_usd: float = 0.0
    subject: str | None = None  # the commit this gate approves
    urgency: str = "none"  # late | soon | none
    seconds_left: int | None = None  # until the gate is due; negative when late
    checks: list[CheckOut] = []
    files: list[ChangedFileOut] = []  # what the approved commit changed


#: audit actions that mean something went wrong or needs a person (the Errors page)
PROBLEM_ACTIONS = frozenset({
    "gate.denied", "gate.expired", "hook.failed", "runner.unavailable",
    "step.failed", "step.blocked", "step.escalated", "step.retry", "run.killed",
})  # fmt: skip


class AuditOut(BaseModel):
    seq: int
    at: str
    run_id: str | None
    step_id: str | None
    actor: str
    action: str
    detail: str


class AuditPage(BaseModel):
    items: list[AuditOut]
    next_cursor: str | None


class TriggerOut(BaseModel):
    provider: str  # jira | github | gitlab
    event: str
    key: str
    label: str  # "PAY-139 in Jira"
    url: str | None  # None when the project has no tracker configured
    title: str | None
    status: str | None


class PageOut(BaseModel):
    id: str
    title: str
    url: str


class ArtifactOut(BaseModel):
    step_id: str
    name: str
    size: int
    sha256: str
    at: str


class SpendOut(BaseModel):
    tokens: int
    cost_usd: float


class RunDetail(BaseModel):
    run: RunOut
    artifacts: list[ArtifactOut] = []
    spend: SpendOut = SpendOut(tokens=0, cost_usd=0.0)
    trigger: TriggerOut | None = None
    evidence: list[EvidenceOut]
    gates: list[GateOut]
    audit: list[AuditOut]


class Decision(BaseModel):
    decision: Literal["approve", "reject"]
    comment: str = Field("", max_length=500)


class DecisionResult(BaseModel):
    gate: GateOut
    resumed: str


class PipelineStepOut(BaseModel):
    id: str
    agent: str | None
    depends_on: list[str]
    gate_role: str | None
    requires: list[str]
    produces: list[str]


class PlanStepOut(BaseModel):
    id: str
    level: int
    agent: str
    mode: str
    gate: str | None
    estimated_tokens: int


class PlanOut(BaseModel):
    pipeline: str
    steps: list[PlanStepOut]
    estimated_tokens: int
    budget_tokens: int | None
    over_budget: bool


class StartRun(BaseModel):
    pipeline: str = Field(max_length=100)


class StartedRun(BaseModel):
    run_id: str


class PipelineOut(BaseModel):
    name: str
    steps: list[PipelineStepOut]


class VariableOut(BaseModel):
    key: str
    value: str
    secret: bool


class VariableIn(BaseModel):
    value: str = Field(max_length=2000)


class UserOut(BaseModel):
    subject: str
    name: str
    claims: list[str]
    last_login: str


class MappingIn(BaseModel):
    claim: str = Field(min_length=1, max_length=200)
    role: Literal["owner", "product_owner", "qa", "developer", "reader"]


class MappingOut(BaseModel):
    claim: str
    role: str


class ProjectIn(BaseModel):
    id: str = Field(pattern=PROJECT_ID.pattern)
    name: str = Field(min_length=1, max_length=120)
    manifest: str = Field(min_length=1, max_length=500)
    team: str | None = Field(default=None, max_length=120)
    repo: str | None = Field(default=None, max_length=500)
    access: list[str] = Field(default_factory=list, max_length=50)


class ProjectUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    manifest: str = Field(min_length=1, max_length=500)
    team: str | None = Field(default=None, max_length=120)
    repo: str | None = Field(default=None, max_length=500)
    access: list[str] = Field(default_factory=list, max_length=50)


class ProjectAdminOut(BaseModel):
    id: str
    name: str
    manifest: str
    team: str | None
    repo: str | None
    access: list[str]
    archived: bool


class OrganizationIO(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    org_roles: list[str] = Field(default_factory=list, max_length=50)


class AdminEventOut(BaseModel):
    seq: int
    at: str
    actor: str
    action: str
    detail: str


class ProbeIn(BaseModel):
    key: str


class ProbeOut(BaseModel):
    ok: bool
    detail: str


RunOut.model_rebuild()


class FindingOut(BaseModel):
    severity: str
    code: str
    path: str
    message: str


class SourceOut(BaseModel):
    path: str
    content: str
    commit: str
    branch: str


class ValidateIn(BaseModel):
    content: str = Field(max_length=262144)


class ValidateOut(BaseModel):
    ok: bool
    findings: list[FindingOut]
    pipelines: list[PipelineOut] = []


class DraftOut(BaseModel):
    id: str
    status: str
    path: str
    base_sha: str
    content: str
    author: str
    created_at: str
    updated_at: str
    branch: str | None = None
    change_request_url: str | None = None
    diff: str


class ConflictOut(BaseModel):
    title: str
    status: int
    detail: str
    diff: str
    current_sha: str


# --- dependencies from the portal ------------------------------------------------------


@dataclass
class ApiDeps:
    """What the API borrows from the portal app: one auth model, not two."""

    scope: Callable[[Request, str], tuple[dict[str, Any], Project, Directory, set[str]]]
    session: Callable[[Request], tuple[str, dict[str, Any]]]
    directory: Callable[[], Directory]
    registry: ProjectRegistry
    visible: Callable[[Project, Directory, set[str]], bool]
    roles_in: Callable[[Project, Directory, set[str]], set[str]]
    open_store: Callable[[Project], AbstractContextManager[StateStore]]
    resume: Callable[[StateStore, Project, str], str]
    #: create a run through the engine (worktree, audit): (store, project, pipeline, run id, who)
    create: Callable[[StateStore, Project, str, str, str], None]
    logout: Callable[[str], None]
    decision_allowed: Callable[[str], bool]
    now: Callable[[], str]
    vars_store: Callable[[Project], VarsStore]
    probe: Callable[[str], tuple[bool, str]]
    admin: AdminStore
    drafts: DraftStore
    forge: Callable[[Project], Forge | None]
    tracker: Callable[[Project], Tracker | None]
    wiki: Callable[[Project], Wiki | None]
    artifacts: Callable[[Project], ArtifactStore]
    login_options: Callable[[], LoginOptions]
    #: runs a job without blocking the request (a thread in the portal, inline in tests)
    spawn: Callable[[Callable[[], None]], None] = lambda fn: fn()


def _problem(status: int, title: str, detail: str | None = None) -> JSONResponse:
    body = Problem(title=title, status=status, detail=detail).model_dump(exclude_none=True)
    return JSONResponse(body, status_code=status, media_type=PROBLEM)


def outline(manifest: Manifest) -> list[PipelineOut]:
    out: list[PipelineOut] = []
    for name, pipe in manifest.pipelines.items():
        steps = []
        for sid in topo_order(pipe.steps):
            s = pipe.steps[sid]
            steps.append(
                PipelineStepOut(
                    id=sid,
                    agent=s.agent,
                    depends_on=list(s.dependsOn),
                    gate_role=s.gate.role if s.gate is not None else None,
                    requires=list(s.requiresEvidence),
                    produces=list(s.producesEvidence),
                )
            )
        out.append(PipelineOut(name=name, steps=steps))
    return out


def encode_cursor(value: int) -> str:
    return base64.urlsafe_b64encode(str(value).encode()).decode().rstrip("=")


def decode_cursor(cursor: str | None) -> int:
    if not cursor:
        return 0
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
        value = int(raw)
    except (ValueError, binascii.Error):
        raise HTTPException(400, "invalid cursor") from None
    if value < 0:
        raise HTTPException(400, "invalid cursor")
    return value


def create_api(deps: ApiDeps) -> FastAPI:
    api = FastAPI(
        title="ASAC portal API",
        version="1",
        docs_url=None,
        redoc_url=None,
        openapi_url="/openapi.json",
    )

    @api.exception_handler(HTTPException)
    async def http_error(_: Request, exc: HTTPException) -> JSONResponse:
        if exc.status_code == 303:  # the page flow redirects to /login; an API says 401
            return _problem(401, "Authentication required")
        titles = {
            400: "Bad request",
            401: "Authentication required",
            403: "Forbidden",
            404: "Not found",
            409: "Conflict",
            429: "Too many requests",
            503: "Service unavailable",
        }
        return _problem(exc.status_code, titles.get(exc.status_code, "Error"), str(exc.detail))

    @api.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        fields = ", ".join(".".join(str(p) for p in e["loc"]) for e in exc.errors())
        return _problem(422, "Invalid request", f"check: {fields}")

    @api.exception_handler(Exception)
    async def unexpected(_: Request, __: Exception) -> JSONResponse:
        return _problem(500, "Internal error")  # never leak the exception text

    def user_roles(data: dict[str, Any]) -> set[str]:
        return set(data["user"]["roles"])

    def run_out(store: StateStore, run_id: str, manifest_order: list[str] | None = None) -> RunOut:
        rec = store.get_run(run_id)
        steps = store.list_steps(run_id)
        order = manifest_order or list(steps)
        ids = [s for s in order if s in steps] + [s for s in steps if s not in order]
        return RunOut(
            run_id=rec.run_id,
            pipeline=rec.pipeline,
            status=rec.status,
            created_at=rec.created_at,
            steps=[StepOut(id=s, status=steps[s]) for s in ids],
        )

    def gate_out(g: Any, roles: set[str]) -> GateOut:
        return GateOut(
            gate_id=g.gate_id,
            run_id=g.run_id,
            step_id=g.step_id,
            type=g.type,
            role=g.role,
            status=g.status,
            requested_at=g.requested_at,
            timeout_at=g.timeout_at,
            decided_by=g.decided_by,
            decided_at=g.decided_at,
            comment=g.comment,
            can_decide=g.status == "pending" and (not g.role or g.role in roles),
        )

    def audit_out(a: Any) -> AuditOut:
        return AuditOut(
            seq=a.seq, at=a.at, run_id=a.run_id, step_id=a.step_id,
            actor=a.actor, action=a.action, detail=a.detail,
        )  # fmt: skip

    @api.get("/login-options", response_model=LoginOptions, operation_id="getLoginOptions")
    def login_options() -> LoginOptions:
        """Public: what the sign-in screen offers. No session, no secrets."""
        return deps.login_options()

    @api.get("/me", response_model=Me, operation_id="getMe")
    def me(request: Request) -> Me:
        _, data = deps.session(request)
        d = deps.directory()
        u = data["user"]
        return Me(
            sub=u["sub"], name=u["name"], roles=sorted(u["roles"]), csrf=data["csrf"],
            organization=d.organization,
        )  # fmt: skip

    @api.get("/projects", response_model=list[ProjectOut], operation_id="listProjects")
    def projects(request: Request) -> list[ProjectOut]:
        _, data = deps.session(request)
        d = deps.directory()
        claims = user_roles(data)
        out: list[ProjectOut] = []
        for p in d.projects:
            if not deps.visible(p, d, claims):
                continue
            roles = deps.roles_in(p, d, claims)
            base = {"id": p.id, "name": p.name, "team": p.team, "repo": p.repo,
                    "roles": sorted(roles)}  # fmt: skip
            try:
                with deps.open_store(p) as store:
                    runs = store.list_runs()
                    waiting = store.list_gates("pending")
            except Exception:  # one broken project must not hide the others
                out.append(ProjectOut(**base, active_runs=0, problem_runs=0, pending_gates=0,
                                      my_pending_gates=0, error=True))  # fmt: skip
                continue
            out.append(
                ProjectOut(
                    **base,
                    active_runs=sum(r.status in ("running", "gate_waiting") for r in runs),
                    problem_runs=sum(r.status in ("blocked", "failed", "killed") for r in runs),
                    pending_gates=len(waiting),
                    my_pending_gates=sum(1 for g in waiting if not g.role or g.role in roles),
                )
            )
        return out

    @api.get("/overview", response_model=OverviewOut, operation_id="getOverview")
    def overview(request: Request) -> OverviewOut:
        """Every project the person can see, summed. All figures are declared (see the design)."""
        _, data = deps.session(request)
        d = deps.directory()
        claims = user_roles(data)
        rows: list[ProjectFiguresOut] = []
        for p in d.projects:
            if not deps.visible(p, d, claims):
                continue
            try:
                with deps.open_store(p) as store:
                    runs = store.list_runs()
                    pending = len(store.list_gates("pending"))
                    audits = [(r.run_id, store.audit(r.run_id)) for r in runs]
                fig = figures_for(p.id, p.name, p.team, runs, audits, pending)
            except Exception:  # one broken project must not hide the others
                fig = unavailable(p.id, p.name, p.team)
            rows.append(ProjectFiguresOut(**fig.__dict__, check_pass_rate=fig.check_pass_rate))
        keys = ("runs", "active", "problems", "pending_gates", "cost_usd", "tokens",
                "integrity_violations", "sandbox_denials")  # fmt: skip
        totals = {k: round(sum(getattr(r, k) for r in rows if not r.unavailable), 4) for k in keys}
        return OverviewOut(assurance="declared", projects=rows, totals=totals)

    def files_of(p: Project, g: Any, rows: list[Any]) -> list[Any]:
        """Files of the approved commit, read in the run's own worktree (never the main one)."""
        if not g.subject:
            return []
        try:
            with deps.open_store(p) as store:
                work = recorded_workspace(store, g.run_id)
        except Exception:
            return []
        return changed_files(work, g.subject, p.manifest.parent) if work is not None else []

    def decision_item(p: Project, g: Any, base: GateOut) -> PendingDecision:
        """A pending gate with what the person needs: urgency, cost, commit and checks."""
        try:
            with deps.open_store(p) as store:
                rows = store.audit(g.run_id)
                pipeline = store.get_run(g.run_id).pipeline
        except Exception:  # a run that cannot be read still shows its gate
            rows, pipeline = [], ""
        level, left = urgency(g.timeout_at, deps.now())
        return PendingDecision(
            **base.model_dump(),
            project_id=p.id,
            project_name=p.name,
            pipeline=pipeline,
            run_started_at=started_at(rows),
            cost_usd=spend_of(rows).cost_usd,
            subject=g.subject,
            urgency=level,
            seconds_left=left,
            checks=[CheckOut(**c.__dict__) for c in checks_from_audit(rows, g.step_id)],
            files=[ChangedFileOut(**f.__dict__) for f in files_of(p, g, rows)],
        )

    @api.get("/decisions", response_model=list[PendingDecision], operation_id="listDecisions")
    def decisions(
        request: Request, project: str | None = None, mine: bool = False
    ) -> list[PendingDecision]:
        """Pending gates of every visible project (or one), oldest first.

        ``mine`` keeps only the gates the signed-in user's roles allow them to decide.
        """
        _, data = deps.session(request)
        d = deps.directory()
        claims = user_roles(data)
        out: list[PendingDecision] = []
        for p in d.projects:
            if (project and p.id != project) or not deps.visible(p, d, claims):
                continue
            roles = deps.roles_in(p, d, claims)
            try:
                with deps.open_store(p) as store:
                    waiting = store.list_gates("pending")
            except Exception:  # one broken project must not hide the others
                continue
            for g in waiting:
                base = gate_out(g, roles)
                if mine and not base.can_decide:
                    continue
                out.append(decision_item(p, g, base))
        return sorted(out, key=lambda x: x.requested_at)

    @api.get("/projects/{pid}/runs", response_model=RunPage, operation_id="listRuns")
    def runs(
        request: Request,
        pid: str,
        status: str = "",
        pipeline: str = "",
        q: str = Query("", max_length=100),
        cursor: str | None = None,
        limit: int = Query(25, ge=1, le=100),
    ) -> RunPage:
        _, project, _, _ = deps.scope(request, pid)
        offset = decode_cursor(cursor)
        manifest = load_manifest(project.manifest)
        needle = q.strip().lower()
        with deps.open_store(project) as store:
            ordered = sorted(store.list_runs(), key=lambda r: r.created_at, reverse=True)
            shown = [
                r for r in ordered
                if (not status or r.status == status)
                and (not pipeline or r.pipeline == pipeline)
                and (not needle or needle in r.run_id.lower() or needle in r.pipeline.lower())
            ]  # fmt: skip
            window = shown[offset : offset + limit]
            items = []
            for r in window:
                pipe = manifest.pipelines.get(r.pipeline)
                items.append(run_out(store, r.run_id, topo_order(pipe.steps) if pipe else None))
        more = offset + limit < len(shown)
        return RunPage(items=items, next_cursor=encode_cursor(offset + limit) if more else None)

    def trigger_out(project: Project, audit: list[Any]) -> TriggerOut | None:
        """Where the run came from, from the daemon's ``run.triggered`` audit entry. The link
        needs no network call; title and status are best effort and never fail the page."""
        for a in audit:
            if a.action != "run.triggered":
                continue
            provider, _, rest = str(a.detail).partition(":")
            key, _, event = rest.partition(":")
            tracker: Tracker | None = None
            with suppress(TrackerError):
                tracker = deps.tracker(project)
            if tracker is not None and tracker.provider != provider:
                tracker = None  # the project's tracker is not where this event came from
            label = f"{key} in {tracker.name if tracker else provider.capitalize()}"
            url = title = status = None
            if tracker is not None and tracker.valid_key(key):
                url = tracker.issue_url(key)
                try:
                    issue = tracker.get_issue(key)
                    title, status = issue.title, issue.status
                except TrackerError:
                    pass
            return TriggerOut(
                provider=provider, event=event, key=key, label=label,
                url=url, title=title, status=status,
            )  # fmt: skip
        return None

    def artifacts_of(project: Project, run_id: str) -> list[ArtifactOut]:
        try:
            items = deps.artifacts(project).list(run_id)
        except ArtifactError:
            return []
        return [
            ArtifactOut(step_id=a.step_id, name=a.name, size=a.size, sha256=a.sha256, at=a.at)
            for a in items
        ]

    def spend_of(rows: list[Any]) -> SpendOut:
        spend = RunState(rows).spend  # the one reading of the audit, shared with the engine
        return SpendOut(tokens=spend.tokens, cost_usd=round(spend.cost_usd, 4))

    @api.get(
        "/projects/{pid}/runs/{run_id}/artifacts/{name}",
        operation_id="downloadArtifact",
        response_class=Response,
        responses={200: {"content": {"application/octet-stream": {}}}},
    )
    def download_artifact(request: Request, pid: str, run_id: str, name: str) -> Response:
        _, project, _, _ = deps.scope(request, pid)
        try:
            data = deps.artifacts(project).read(run_id, name)
        except ArtifactError:
            raise HTTPException(404, "unknown artifact") from None
        return Response(
            data,
            media_type="application/octet-stream",
            headers={
                "Content-Disposition": f'attachment; filename="{name}"',
                "X-Content-Type-Options": "nosniff",
            },
        )

    @api.get("/projects/{pid}/runs/{run_id}", response_model=RunDetail, operation_id="getRun")
    def run_detail(request: Request, pid: str, run_id: str) -> RunDetail:
        _, project, _, roles = deps.scope(request, pid)
        manifest = load_manifest(project.manifest)
        with deps.open_store(project) as store:
            try:
                rec = store.get_run(run_id)
            except NotFound:
                raise HTTPException(404, "unknown run") from None
            pipe = manifest.pipelines.get(rec.pipeline)
            audit_rows = store.audit(run_id)
            return RunDetail(
                artifacts=artifacts_of(project, run_id),
                spend=spend_of(audit_rows),
                run=run_out(store, run_id, topo_order(pipe.steps) if pipe else None),
                trigger=trigger_out(project, audit_rows),
                evidence=[
                    EvidenceOut(
                        evidence_id=e.evidence_id,
                        produced_by=e.produced_by,
                        approved_by=e.approved_by,
                        bootstrapped=e.bootstrapped,
                        at=e.at,
                    )
                    for e in store.list_evidence(run_id)
                ],
                gates=[gate_out(g, roles) for g in store.list_gates() if g.run_id == run_id],
                audit=[audit_out(a) for a in audit_rows],
            )

    @api.get("/projects/{pid}/gates", response_model=list[GateOut], operation_id="listGates")
    def gates(request: Request, pid: str, status: str = "") -> list[GateOut]:
        _, project, _, roles = deps.scope(request, pid)
        with deps.open_store(project) as store:
            items = store.list_gates()
        ordered = sorted(items, key=lambda g: (g.status != "pending", g.requested_at))
        return [gate_out(g, roles) for g in ordered if not status or g.status == status]

    @api.post(
        "/projects/{pid}/gates/{gate_id}/decision",
        response_model=DecisionResult,
        operation_id="decideGate",
    )
    def decide(
        request: Request,
        pid: str,
        gate_id: str,
        body: Decision,
        x_csrf_token: str = Header(""),
    ) -> DecisionResult:
        data, project, _, roles = deps.scope(request, pid)
        if not secrets.compare_digest(str(data.get("csrf", "")), x_csrf_token):
            raise HTTPException(403, "invalid CSRF token")
        user = data["user"]
        if not deps.decision_allowed(str(user["sub"])):
            raise HTTPException(429, "too many decisions")
        who = f"{user['name']} ({user['sub']})"
        status: Literal["approved", "rejected"] = (
            "approved" if body.decision == "approve" else "rejected"
        )
        with deps.open_store(project) as store:
            try:
                gate = decide_gate(
                    store, gate_id, status, who, roles, body.comment or None, actor="portal"
                )
            except Forbidden as exc:
                try:
                    run_id = store.get_gate(gate_id).run_id
                except NotFound:
                    run_id = None
                store.append_audit(
                    run_id, who, "gate.denied", deps.now(),
                    detail=f"{gate_id}: {exc}; roles={','.join(sorted(roles))}",
                )  # fmt: skip
                raise HTTPException(403, str(exc)) from None
            except NotFound:
                raise HTTPException(404, "unknown gate") from None
            except (GateError, StateError) as exc:
                raise HTTPException(409, str(exc)) from None
            resumed = deps.resume(store, project, gate.run_id)
            return DecisionResult(gate=gate_out(gate, roles), resumed=resumed)

    @api.post("/logout", status_code=204, operation_id="logout")
    def logout(request: Request, x_csrf_token: str = Header("")) -> Response:
        sid, data = deps.session(request)
        if not secrets.compare_digest(str(data.get("csrf", "")), x_csrf_token):
            raise HTTPException(403, "invalid CSRF token")
        deps.logout(sid)
        resp = Response(status_code=204)
        resp.delete_cookie("asac_session", path="/")
        return resp

    @api.get("/projects/{pid}/audit.csv", operation_id="exportAudit")
    def audit_csv(request: Request, pid: str) -> Response:
        data, project, d, roles = deps.scope(request, pid)
        if not ({"auditor", "manager"} & roles or d.org_roles & set(data["user"]["roles"])):
            raise HTTPException(403, "export requires the auditor or manager role")
        buf = io.StringIO()
        w = csv.writer(buf, lineterminator="\n")
        w.writerow(["seq", "at", "run_id", "step_id", "actor", "action", "detail"])
        with deps.open_store(project) as store:
            for a in store.audit(None):
                w.writerow(
                    [a.seq, a.at, a.run_id or "", a.step_id or "", a.actor, a.action, a.detail]
                )
        return Response(
            buf.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{pid}-audit.csv"'},
        )

    @api.get("/projects/{pid}/audit", response_model=AuditPage, operation_id="listAudit")
    def audit(
        request: Request,
        pid: str,
        cursor: str | None = None,
        limit: int = Query(50, ge=1, le=200),
        problems: bool = False,
    ) -> AuditPage:
        _, project, _, _ = deps.scope(request, pid)
        offset = decode_cursor(cursor)
        with deps.open_store(project) as store:
            records = list(reversed(store.audit(None)))
        if problems:
            records = [a for a in records if a.action in PROBLEM_ACTIONS]
        window = records[offset : offset + limit]
        more = offset + limit < len(records)
        return AuditPage(
            items=[audit_out(a) for a in window],
            next_cursor=encode_cursor(offset + limit) if more else None,
        )

    @api.get(
        "/projects/{pid}/pipelines", response_model=list[PipelineOut], operation_id="listPipelines"
    )
    def pipelines(request: Request, pid: str) -> list[PipelineOut]:
        _, project, _, _ = deps.scope(request, pid)
        return outline(load_manifest(project.manifest))

    @api.get(
        "/projects/{pid}/pipelines/{name}/plan", response_model=PlanOut, operation_id="planPipeline"
    )
    def plan_pipeline(request: Request, pid: str, name: str) -> PlanOut:
        _, project, _, _ = deps.scope(request, pid)
        manifest = load_manifest(project.manifest)
        if name not in manifest.pipelines:
            raise HTTPException(404, "unknown pipeline")
        p = build_plan(manifest, name)
        return PlanOut(
            pipeline=p.pipeline,
            steps=[
                PlanStepOut(
                    id=x.id, level=x.level, agent=x.agent, mode=x.mode, gate=x.gate,
                    estimated_tokens=x.estimated_tokens,
                )
                for x in p.steps
            ],
            estimated_tokens=p.estimated_tokens,
            budget_tokens=p.budget_tokens,
            over_budget=p.over_budget,
        )  # fmt: skip

    def run_guard(request: Request, pid: str, csrf: str) -> tuple[Project, str]:
        data, project, _, roles = deps.scope(request, pid)
        if not secrets.compare_digest(str(data.get("csrf", "")), csrf):
            raise HTTPException(403, "invalid CSRF token")
        if not (roles & RUN_STARTERS or "admin" in user_roles(data)):
            raise HTTPException(
                403, "starting or stopping a run requires developer, owner or admin"
            )
        u = data["user"]
        return project, f"{u['name']} ({u['sub']})"

    @api.post(
        "/projects/{pid}/runs",
        response_model=StartedRun,
        status_code=202,
        operation_id="startRun",
    )
    def start_run(
        request: Request, pid: str, body: StartRun, x_csrf_token: str = Header("")
    ) -> StartedRun:
        project, who = run_guard(request, pid, x_csrf_token)
        manifest = load_manifest(project.manifest)
        if body.pipeline not in manifest.pipelines:
            raise HTTPException(404, "unknown pipeline")
        if build_plan(manifest, body.pipeline).over_budget:
            raise HTTPException(409, "the estimated cost is over the run budget")
        with deps.open_store(project) as store:
            taken = {r.run_id for r in store.list_runs()}
            n = len(taken) + 1
            while f"run_{body.pipeline}_{n:04d}" in taken:
                n += 1
            run_id = f"run_{body.pipeline}_{n:04d}"
            # Through the engine, like `asac apply`: it creates the run's worktree. Creating the
            # row by hand left the agent working in the main checkout, unisolated.
            try:
                deps.create(store, project, body.pipeline, run_id, who)
            except StateError as exc:
                raise HTTPException(409, str(exc)) from None

        def job() -> None:
            with deps.open_store(project) as s:
                deps.resume(s, project, run_id)

        deps.spawn(job)
        return StartedRun(run_id=run_id)

    @api.post("/projects/{pid}/runs/{run_id}/stop", status_code=204, operation_id="stopRun")
    def stop_run(request: Request, pid: str, run_id: str, x_csrf_token: str = Header("")) -> None:
        project, who = run_guard(request, pid, x_csrf_token)
        with deps.open_store(project) as store:
            try:
                rec = store.get_run(run_id)
            except NotFound:
                raise HTTPException(404, "unknown run") from None
            if rec.status in ("completed", "killed"):
                raise HTTPException(409, f"run is already {rec.status}")
            store.set_run_status(run_id, "killed")
            store.append_audit(
                run_id, who, "run.killed", deps.now(), detail="stopped from the portal"
            )

    def vars_guard(request: Request, pid: str, write: bool, csrf: str = "") -> Project:
        data, project, _, roles = deps.scope(request, pid)
        if write:
            if not secrets.compare_digest(str(data.get("csrf", "")), csrf):
                raise HTTPException(403, "invalid CSRF token")
            if not (roles & VARS_WRITERS or "admin" in user_roles(data)):
                raise HTTPException(403, "changing variables requires the owner or admin role")
        return project

    @api.get(
        "/projects/{pid}/variables", response_model=list[VariableOut], operation_id="listVariables"
    )
    def list_variables(request: Request, pid: str) -> list[VariableOut]:
        project = vars_guard(request, pid, write=False)
        try:
            items = deps.vars_store(project).list()
        except VarsError as exc:
            raise HTTPException(409, str(exc)) from None
        return [VariableOut(key=v.key, value=v.value, secret=v.secret) for v in items]

    @api.put(
        "/projects/{pid}/variables/{key}", response_model=VariableOut, operation_id="setVariable"
    )
    def set_variable(
        request: Request, pid: str, key: str, body: VariableIn, x_csrf_token: str = Header("")
    ) -> VariableOut:
        project = vars_guard(request, pid, write=True, csrf=x_csrf_token)
        try:
            v = deps.vars_store(project).set(key, body.value)
        except VarsError as exc:
            raise HTTPException(422, str(exc)) from None
        with deps.open_store(project) as store:
            user = deps.session(request)[1]["user"]
            store.append_audit(
                None, f"{user['name']} ({user['sub']})", "variable.set", deps.now(), detail=key
            )
        return VariableOut(key=v.key, value=v.value, secret=v.secret)

    @api.delete("/projects/{pid}/variables/{key}", status_code=204, operation_id="deleteVariable")
    def delete_variable(
        request: Request, pid: str, key: str, x_csrf_token: str = Header("")
    ) -> None:
        project = vars_guard(request, pid, write=True, csrf=x_csrf_token)
        try:
            deps.vars_store(project).delete(key)
        except VarsError as exc:
            raise HTTPException(404, str(exc)) from None
        with deps.open_store(project) as store:
            user = deps.session(request)[1]["user"]
            store.append_audit(
                None, f"{user['name']} ({user['sub']})", "variable.deleted", deps.now(), detail=key
            )

    @api.post(
        "/projects/{pid}/connections/test", response_model=ProbeOut, operation_id="testConnection"
    )
    def test_connection(
        request: Request, pid: str, body: ProbeIn, x_csrf_token: str = Header("")
    ) -> ProbeOut:
        project = vars_guard(request, pid, write=True, csrf=x_csrf_token)
        found = {v.key: v for v in deps.vars_store(project).list()}
        var = found.get(body.key)
        if var is None or var.secret:
            raise HTTPException(404, "no URL variable with that key")
        ok, detail = deps.probe(var.value)
        return ProbeOut(ok=ok, detail=detail)

    @api.get("/projects/{pid}/wiki/pages", response_model=list[PageOut], operation_id="searchWiki")
    def search_wiki(
        request: Request, pid: str, q: str = Query("", max_length=100)
    ) -> list[PageOut]:
        _, project, _, _ = deps.scope(request, pid)
        try:
            wiki = deps.wiki(project)
            if wiki is None:
                raise HTTPException(409, "no wiki is configured for this project (see Variables)")
            return [PageOut(id=p.id, title=p.title, url=p.url) for p in wiki.search(q, 10)]
        except WikiError as exc:
            raise HTTPException(502, str(exc)) from None

    # --- administration: org admin, or project owner for that project's mappings -------------

    def who_of(request: Request) -> str:
        u = deps.session(request)[1]["user"]
        return f"{u['name']} ({u['sub']})"

    def require_admin(request: Request) -> None:
        _, data = deps.session(request)
        if "admin" not in user_roles(data):
            raise HTTPException(403, "requires the organisation admin role")

    def mapping_guard(request: Request, pid: str, csrf: str | None) -> Project:
        data, project, _, roles = deps.scope(request, pid)
        if csrf is not None and not secrets.compare_digest(str(data.get("csrf", "")), csrf):
            raise HTTPException(403, "invalid CSRF token")
        if not ("owner" in roles or "admin" in user_roles(data)):
            raise HTTPException(403, "requires the project owner or organisation admin role")
        return project

    @api.get("/admin/users", response_model=list[UserOut], operation_id="listUsers")
    def list_users(request: Request) -> list[UserOut]:
        require_admin(request)
        return [
            UserOut(subject=u.subject, name=u.name, claims=list(u.claims), last_login=u.last_login)
            for u in deps.admin.list_users()
        ]

    @api.get("/admin/events", response_model=list[AdminEventOut], operation_id="listAdminEvents")
    def admin_events(request: Request) -> list[AdminEventOut]:
        require_admin(request)
        return [
            AdminEventOut(seq=e.seq, at=e.at, actor=e.actor, action=e.action, detail=e.detail)
            for e in deps.admin.events()
        ]

    def admin_csrf(request: Request, csrf: str) -> None:
        require_admin(request)
        data = deps.session(request)[1]
        if not secrets.compare_digest(str(data.get("csrf", "")), csrf):
            raise HTTPException(403, "invalid CSRF token")

    def project_out(p: Project) -> ProjectAdminOut:
        return ProjectAdminOut(
            id=p.id, name=p.name, manifest=str(p.manifest), team=p.team, repo=p.repo,
            access=sorted(p.access), archived=p.archived,
        )  # fmt: skip

    def manifest_path(raw: str) -> Path:
        path = Path(raw).expanduser()
        if not path.is_absolute() or path.suffix not in (".yaml", ".yml"):
            raise HTTPException(422, "manifest must be an absolute path to a YAML file")
        if not path.is_file():
            raise HTTPException(422, f"manifest not found: {path}")
        return path.resolve()

    @api.get(
        "/admin/projects", response_model=list[ProjectAdminOut], operation_id="listAdminProjects"
    )
    def admin_projects(request: Request) -> list[ProjectAdminOut]:
        require_admin(request)
        return [project_out(p) for p in deps.registry.load(include_archived=True).projects]

    @api.post(
        "/admin/projects", response_model=ProjectAdminOut, status_code=201,
        operation_id="createProject",
    )  # fmt: skip
    def create_project(
        request: Request, body: ProjectIn, x_csrf_token: str = Header("")
    ) -> ProjectAdminOut:
        admin_csrf(request, x_csrf_token)
        project = Project(
            id=body.id, name=body.name, manifest=manifest_path(body.manifest), team=body.team,
            repo=body.repo, access=frozenset(body.access),
        )  # fmt: skip
        try:
            deps.registry.create(project)
        except ProjectError as exc:
            raise HTTPException(409, str(exc)) from None
        deps.admin.append_event(who_of(request), "project.created", deps.now(), project.id)
        return project_out(project)

    @api.put("/admin/projects/{pid}", response_model=ProjectAdminOut, operation_id="updateProject")
    def update_project(
        request: Request, pid: str, body: ProjectUpdate, x_csrf_token: str = Header("")
    ) -> ProjectAdminOut:
        admin_csrf(request, x_csrf_token)
        project = Project(
            id=pid, name=body.name, manifest=manifest_path(body.manifest), team=body.team,
            repo=body.repo, access=frozenset(body.access),
        )  # fmt: skip
        try:
            deps.registry.update(project)
        except ProjectError as exc:
            raise HTTPException(404, str(exc)) from None
        deps.admin.append_event(who_of(request), "project.updated", deps.now(), pid)
        return project_out(project)

    @api.post("/admin/projects/{pid}/archive", status_code=204, operation_id="archiveProject")
    def archive_project(request: Request, pid: str, x_csrf_token: str = Header("")) -> None:
        _set_archived(request, pid, x_csrf_token, True)

    @api.post("/admin/projects/{pid}/restore", status_code=204, operation_id="restoreProject")
    def restore_project(request: Request, pid: str, x_csrf_token: str = Header("")) -> None:
        _set_archived(request, pid, x_csrf_token, False)

    def _set_archived(request: Request, pid: str, csrf: str, archived: bool) -> None:
        admin_csrf(request, csrf)
        try:
            deps.registry.set_archived(pid, archived)
        except ProjectError as exc:
            raise HTTPException(404, str(exc)) from None
        deps.admin.append_event(
            who_of(request), "project.archived" if archived else "project.restored",
            deps.now(), pid,
        )  # fmt: skip

    @api.put("/admin/organization", response_model=OrganizationIO, operation_id="setOrganization")
    def set_organization(
        request: Request, body: OrganizationIO, x_csrf_token: str = Header("")
    ) -> OrganizationIO:
        admin_csrf(request, x_csrf_token)
        deps.registry.set_organization(body.name, frozenset(body.org_roles))
        deps.admin.append_event(
            who_of(request), "organization.updated", deps.now(),
            f"{body.name}; org_roles={','.join(sorted(body.org_roles))}",
        )  # fmt: skip
        return body

    @api.get("/admin/organization", response_model=OrganizationIO, operation_id="getOrganization")
    def get_organization(request: Request) -> OrganizationIO:
        require_admin(request)
        d = deps.registry.load()
        return OrganizationIO(name=d.organization, org_roles=sorted(d.org_roles))

    @api.get(
        "/projects/{pid}/mappings", response_model=list[MappingOut], operation_id="listMappings"
    )
    def list_mappings(request: Request, pid: str) -> list[MappingOut]:
        mapping_guard(request, pid, None)
        return [MappingOut(claim=m.claim, role=m.role) for m in deps.admin.list_mappings(pid)]

    @api.post(
        "/projects/{pid}/mappings",
        response_model=MappingOut,
        status_code=201,
        operation_id="addMapping",
    )
    def add_mapping(
        request: Request, pid: str, body: MappingIn, x_csrf_token: str = Header("")
    ) -> MappingOut:
        mapping_guard(request, pid, x_csrf_token)
        assert body.role in PROJECT_ROLES
        if not deps.admin.add_mapping(Mapping(body.claim, pid, body.role)):
            raise HTTPException(409, "that mapping already exists")
        deps.admin.append_event(
            who_of(request), "mapping.added", deps.now(), f"{pid}: {body.claim} -> {body.role}"
        )
        return MappingOut(claim=body.claim, role=body.role)

    @api.delete(
        "/projects/{pid}/mappings/{claim}/{role}", status_code=204, operation_id="removeMapping"
    )
    def remove_mapping(
        request: Request, pid: str, claim: str, role: str, x_csrf_token: str = Header("")
    ) -> None:
        mapping_guard(request, pid, x_csrf_token)
        if not deps.admin.remove_mapping(Mapping(claim, pid, role)):
            raise HTTPException(404, "no such mapping")
        deps.admin.append_event(
            who_of(request), "mapping.removed", deps.now(), f"{pid}: {claim} -> {role}"
        )

    # --- pipeline editor: drafts live in the portal, git is written only by "propose" ---------

    def editor_guard(
        request: Request, pid: str, csrf: str | None
    ) -> tuple[Project, Forge, set[str]]:
        data, project, _, roles = deps.scope(request, pid)
        if csrf is not None and not secrets.compare_digest(str(data.get("csrf", "")), csrf):
            raise HTTPException(403, "invalid CSRF token")
        if csrf is not None and not (roles & PIPELINE_EDITORS or "admin" in user_roles(data)):
            raise HTTPException(403, "editing the pipeline requires developer, owner or admin")
        forge = deps.forge(project)
        if forge is None:
            raise HTTPException(409, "no forge is configured for this project (see Variables)")
        return project, forge, roles

    def forge_call[T](fn: Callable[[], T]) -> T:
        try:
            return fn()
        except ForgeNotFound as exc:
            raise HTTPException(404, str(exc)) from None
        except Unsupported as exc:
            raise HTTPException(409, str(exc)) from None
        except ForgeError as exc:
            raise HTTPException(502, str(exc)) from None

    def draft_out(d: Draft) -> DraftOut:
        return DraftOut(
            id=d.id, status=d.status, path=d.path, base_sha=d.base_sha, content=d.content,
            author=d.author_name, created_at=d.created_at, updated_at=d.updated_at,
            branch=d.branch, change_request_url=d.cr_url,
            diff=unified_diff(d.base_content, d.content, d.path),
        )  # fmt: skip

    def load_draft(project: Project, draft_id: str) -> Draft:
        d = deps.drafts.get(project.id, draft_id)
        if d is None:
            raise HTTPException(404, "no such draft")
        return d

    @api.get(
        "/projects/{pid}/pipeline/source",
        response_model=SourceOut,
        operation_id="getPipelineSource",
    )
    def pipeline_source(request: Request, pid: str) -> SourceOut:
        _, forge, _ = editor_guard(request, pid, None)
        branch = forge_call(forge.default_branch)
        f = forge_call(lambda: forge.read_file(PIPELINE_FILE, branch))
        return SourceOut(path=f.path, content=f.content, commit=f.commit, branch=branch)

    @api.post(
        "/projects/{pid}/pipeline/validate",
        response_model=ValidateOut,
        operation_id="validatePipeline",
    )
    def validate_pipeline(request: Request, pid: str, body: ValidateIn) -> ValidateOut:
        project = deps.scope(request, pid)[1]
        found = validate_text(body.content, project.manifest.parent)
        pipes: list[PipelineOut] = []
        try:  # the graph follows the text as long as the structure parses
            data = yaml.safe_load(body.content)
            pipes = outline(Manifest.model_validate(data))
        except Exception:  # noqa: BLE001 - findings already say what is wrong
            pass
        return ValidateOut(
            ok=not has_errors(found),
            findings=[FindingOut(**vars(f)) for f in found],
            pipelines=pipes,
        )

    @api.get(
        "/projects/{pid}/pipeline/drafts", response_model=list[DraftOut], operation_id="listDrafts"
    )
    def list_drafts(request: Request, pid: str) -> list[DraftOut]:
        project = deps.scope(request, pid)[1]
        return [draft_out(d) for d in deps.drafts.list(project.id)]

    @api.post(
        "/projects/{pid}/pipeline/drafts",
        response_model=DraftOut,
        status_code=201,
        operation_id="createDraft",
    )
    def create_draft(
        request: Request, pid: str, body: ValidateIn, x_csrf_token: str = Header("")
    ) -> DraftOut:
        project, forge, _ = editor_guard(request, pid, x_csrf_token)
        base = forge_call(lambda: forge.read_file(PIPELINE_FILE))
        user = deps.session(request)[1]["user"]
        now = deps.now()
        d = Draft(
            id=secrets.token_hex(4), project_id=project.id, path=base.path, base_sha=base.commit,
            base_content=base.content, content=body.content, status="draft",
            author_sub=user["sub"], author_name=user["name"],
            author_email=f"{user['sub']}@users.noreply.asac", created_at=now, updated_at=now,
        )  # fmt: skip
        deps.drafts.create(d)
        deps.admin.append_event(who_of(request), "pipeline.draft_created", now, f"{pid}: {d.id}")
        return draft_out(d)

    @api.get(
        "/projects/{pid}/pipeline/drafts/{draft_id}",
        response_model=DraftOut,
        operation_id="getDraft",
    )
    def get_draft(request: Request, pid: str, draft_id: str) -> DraftOut:
        project = deps.scope(request, pid)[1]
        d = load_draft(project, draft_id)
        forge = deps.forge(project)
        if forge is not None and d.status == "proposed":
            d = forge_call(lambda: refresh(d, forge, deps.drafts, deps.now()))
        return draft_out(d)

    @api.put(
        "/projects/{pid}/pipeline/drafts/{draft_id}",
        response_model=DraftOut,
        operation_id="saveDraft",
    )
    def save_draft(
        request: Request, pid: str, draft_id: str, body: ValidateIn, x_csrf_token: str = Header("")
    ) -> DraftOut:
        project, _, _ = editor_guard(request, pid, x_csrf_token)
        d = load_draft(project, draft_id)
        sub = deps.session(request)[1]["user"]["sub"]
        if d.author_sub != sub:
            raise HTTPException(403, "only the author can change a draft")
        if d.status != "draft":
            raise HTTPException(409, f"draft is already {d.status}")
        from dataclasses import replace

        d = replace(d, content=body.content, updated_at=deps.now())
        deps.drafts.update(d)
        return draft_out(d)

    @api.post(
        "/projects/{pid}/pipeline/drafts/{draft_id}/propose",
        response_model=DraftOut,
        responses={409: {"model": ConflictOut}},
        operation_id="proposeDraft",
    )
    def propose_draft(
        request: Request, pid: str, draft_id: str, x_csrf_token: str = Header("")
    ) -> Any:
        project, forge, _ = editor_guard(request, pid, x_csrf_token)
        d = load_draft(project, draft_id)
        sub = deps.session(request)[1]["user"]["sub"]
        if d.author_sub != sub:
            raise HTTPException(403, "only the author can propose a draft")
        try:
            target = forge_call(forge.default_branch)
            done = forge_call(
                lambda: propose(d, forge, deps.drafts, project.manifest.parent, target, deps.now())
            )
        except DraftConflict as exc:
            return JSONResponse(
                {
                    "title": "Conflict",
                    "status": 409,
                    "detail": str(exc),
                    "diff": exc.diff,
                    "current_sha": exc.current_sha,
                },
                status_code=409,
                media_type=PROBLEM,
            )
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from None
        deps.admin.append_event(
            who_of(request), "pipeline.proposed", deps.now(), f"{pid}: {done.id} -> {done.cr_url}"
        )
        return draft_out(done)

    return api
