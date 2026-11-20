"""Portal web app. Security: OIDC + PKCE, server-side sessions, CSRF, strict CSP.

The engine re-checks the gate role on every decision; the UI hiding a button is a
convenience, not the control.
"""

from __future__ import annotations

import os
import secrets
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse

from asac.adapters import state_dir
from asac.adapters.admin_sqlite import SqliteAdminStore
from asac.adapters.artifacts_fs import FsArtifactStore
from asac.adapters.drafts_sqlite import SqliteDraftStore
from asac.adapters.forge_factory import forge_from_vars
from asac.adapters.links_factory import tracker_from_vars, wiki_from_vars
from asac.adapters.projects_sqlite import SqliteProjectRegistry
from asac.adapters.vars_file import FileVarsStore
from asac.engine.apply import execute
from asac.engine.runtime import make_context, open_store, project_root
from asac.loader.load import load_manifest
from asac.portal.oidc import Identity, OidcClient, OidcConfig, OidcError, new_verifier
from asac.portal.probe import probe_url
from asac.portal.sessions import RateLimiter, SessionStore
from asac.ports.forge import Forge
from asac.ports.projects import Directory, Project, ProjectRegistry
from asac.ports.state import StateStore
from asac.ports.tracker import Tracker
from asac.ports.wiki import Wiki

HERE = Path(__file__).parent
COOKIE = "asac_session"
AUDIT_PAGE = 50
RUNS_PAGE = 25
CSP = (
    "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; "
    "font-src 'self'; connect-src 'self'; form-action 'self'; "
    "frame-ancestors 'none'; base-uri 'none'"
)
SPA_DIR = HERE / "spa"  # built by `npm run build` in web/; optional


@dataclass
class PortalSettings:
    #: where the portal keeps its own data (sessions, projects, admin, forge cache)
    data_dir: Path = Path(".asac-portal")
    oidc: OidcConfig | None = None
    dev_personas: dict[str, Identity] | None = None  # only honoured with ASAC_ENV=dev
    harness: str | None = None  # harness used to resume a run after an approval
    secure_cookie: bool = True
    session_db: Path | None = None
    projects: ProjectRegistry | None = None  # default: SQLite in data_dir
    #: test or custom wiring: project -> Forge (default: built from the project's variables)
    forge_factory: Callable[[Project], Forge | None] | None = None
    tracker_factory: Callable[[Project], Tracker | None] | None = None
    wiki_factory: Callable[[Project], Wiki | None] | None = None
    run_inline: bool = False  # tests: run a started run in the request instead of a thread


def dev_mode_allowed() -> bool:
    return os.environ.get("ASAC_ENV") == "dev"


def create_app(settings: PortalSettings, oidc_client: OidcClient | None = None) -> FastAPI:
    if settings.dev_personas is not None and not dev_mode_allowed():
        raise RuntimeError("dev personas require ASAC_ENV=dev; refusing to start")
    if settings.oidc is None and settings.dev_personas is None:
        raise RuntimeError("configure OIDC (or dev personas with ASAC_ENV=dev)")
    client = oidc_client or (OidcClient(settings.oidc) if settings.oidc else None)
    root = settings.data_dir.resolve()
    session_db = settings.session_db or (root / "portal-sessions.db")
    session_db.parent.mkdir(parents=True, exist_ok=True)
    registry: ProjectRegistry = settings.projects or SqliteProjectRegistry(
        session_db.parent / "portal-admin.db"
    )
    sessions = SessionStore(session_db)
    login_limit = RateLimiter(limit=10, window=60)
    decision_limit = RateLimiter(limit=30, window=60)
    admin = SqliteAdminStore(session_db.parent / "portal-admin.db")

    app = FastAPI(title="ASAC portal", docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware("http")
    async def security_headers(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        response.headers.setdefault("Content-Security-Policy", CSP)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Cache-Control"] = "no-store"
        if settings.secure_cookie:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response

    def set_cookie(resp: Response, sid: str) -> None:
        resp.set_cookie(
            COOKIE, sid, httponly=True, secure=settings.secure_cookie, samesite="lax", path="/"
        )

    def current(request: Request) -> tuple[str, dict[str, Any]] | None:
        sid = request.cookies.get(COOKIE)
        data = sessions.load(sid)
        if sid and data and "user" in data:
            return sid, data
        return None

    def require(request: Request) -> tuple[str, dict[str, Any]]:
        got = current(request)
        if got is None:
            raise HTTPException(303, headers={"Location": "/login"})
        return got

    def check_csrf(data: dict[str, Any], token: str) -> None:
        if not secrets.compare_digest(str(data.get("csrf", "")), token or ""):
            raise HTTPException(403, "invalid CSRF token")

    def directory() -> Directory:
        return registry.load()

    def roles_in(project: Project, d: Directory, claims: set[str]) -> set[str]:
        """Roles in a project: claims, then mappings set in the portal."""
        roles = set(claims)
        roles |= {m.role for m in admin.list_mappings(project.id) if m.claim in claims}
        return roles

    def visible(project: Project, d: Directory, claims: set[str]) -> bool:
        return (
            (not project.access)
            or bool(project.access & claims)
            or bool(d.org_roles & claims)
            or "admin" in claims
            or any(m.claim in claims for m in admin.list_mappings(project.id))
        )

    def state_key(project: Project) -> str | None:
        return project.id

    def scope(request: Request, pid: str) -> tuple[dict[str, Any], Project, Directory, set[str]]:
        _, data = require(request)
        d = directory()
        claims = set(data["user"]["roles"])
        project = next((p for p in d.projects if p.id == pid), None)
        if project is None or not visible(project, d, claims):
            raise HTTPException(404, "unknown project")  # same answer: do not reveal it exists
        return data, project, d, roles_in(project, d, claims)

    def client_key(request: Request) -> str:
        return request.client.host if request.client else "unknown"

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}  # liveness only: no data, no session needed

    # --- authentication ---------------------------------------------------------------

    @app.get("/login")
    def login(request: Request, persona: str | None = None) -> Response:
        if not login_limit.allow(client_key(request)):
            raise HTTPException(429, "too many login attempts")
        if settings.dev_personas is not None:
            if persona is None or persona not in settings.dev_personas:
                if persona is None:  # the sign-in screen lists the personas
                    return RedirectResponse("/app/", 303)
                return HTMLResponse("unknown persona", 400)
            return _signed_in(settings.dev_personas[persona])
        assert client is not None
        state, nonce, verifier = (
            secrets.token_urlsafe(24),
            secrets.token_urlsafe(24),
            new_verifier(),
        )
        sid = sessions.create({"oidc": {"state": state, "nonce": nonce, "verifier": verifier}})
        resp = RedirectResponse(client.authorization_url(state, nonce, verifier), 303)
        set_cookie(resp, sid)
        return resp

    @app.get("/callback")
    def callback(request: Request, code: str = "", state: str = "") -> Response:
        if client is None:
            raise HTTPException(404)
        sid = request.cookies.get(COOKIE)
        data = sessions.load(sid) or {}
        pending = data.get("oidc")
        if not sid or not isinstance(pending, dict):
            raise HTTPException(400, "no login in progress")
        sessions.delete(sid)  # one-shot: the pre-login session is never reused
        if not code or not secrets.compare_digest(str(pending["state"]), state):
            raise HTTPException(400, "state mismatch")
        try:
            who = client.exchange(code, pending["verifier"], pending["nonce"])
        except OidcError as exc:
            raise HTTPException(401, str(exc)) from None
        return _signed_in(who)

    def _signed_in(who: Identity) -> Response:
        # A fresh session id at login prevents session fixation.
        sid = sessions.create(
            {
                "user": {"sub": who.subject, "name": who.name, "roles": sorted(who.roles)},
                "csrf": secrets.token_urlsafe(32),
            }
        )
        claims = set(who.roles)
        admin.record_login(who.subject, who.name, sorted(who.roles), _now())
        d = directory()
        for project in d.projects:
            if visible(project, d, claims):
                with open_store(project.manifest, state_key(project)) as store:
                    store.append_audit(
                        None,
                        f"{who.name} ({who.subject})",
                        "portal.login",
                        _now(),
                        detail=",".join(sorted(who.roles)),
                    )
        resp = RedirectResponse("/app/", 303)
        set_cookie(resp, sid)
        return resp

    def _resume_with(store: StateStore, project: Project, run_id: str) -> str:
        """An approval resumes the run with the same function as ``asac apply --resume``."""
        try:
            rec = store.get_run(run_id)
            manifest = load_manifest(project.manifest)
            ctx = make_context(
                manifest, rec.pipeline, store, project_root(project.manifest),
                settings.harness, project=state_key(project),
            )  # fmt: skip
            ctx.actor = "portal"
            outcome = execute(ctx, run_id)
        except Exception as exc:  # the decision is recorded; resuming can be retried by CLI
            store.set_run_status(run_id, "gate_waiting")  # never leave a fake "running" state
            return f"Run not resumed: {exc}"
        return f"Run {run_id}: {outcome.message}"

    # --- JSON API for the SPA --------------------------------------------------------------

    from asac.portal.api import ApiDeps, LoginOptions, Persona, create_api

    def _session(request: Request) -> tuple[str, dict[str, Any]]:
        return require(request)

    def _store_of(project: Project) -> Any:
        return open_store(project.manifest, state_key(project))

    def _login_options() -> LoginOptions:
        try:
            org: str | None = directory().organization
        except HTTPException:
            org = None
        if settings.dev_personas is None:
            return LoginOptions(mode="oidc", organization=org)
        return LoginOptions(
            mode="dev",
            organization=org,
            personas=[
                Persona(id=k, name=v.name, roles=sorted(v.roles))
                for k, v in settings.dev_personas.items()
            ],
        )

    api = create_api(
        ApiDeps(
            scope=scope,
            registry=registry,
            session=_session,
            directory=directory,
            visible=visible,
            roles_in=roles_in,
            open_store=_store_of,
            resume=_resume_with,
            logout=lambda sid: sessions.delete(sid),
            spawn=_inline if settings.run_inline else _thread,
            login_options=_login_options,
            decision_allowed=lambda sub: decision_limit.allow(sub),
            now=_now,
            artifacts=lambda p: FsArtifactStore(
                state_dir(project_root(p.manifest), state_key(p)) / "artifacts"
            ),
            vars_store=lambda p: FileVarsStore(p.manifest.parent / "asac.vars.yaml"),
            probe=probe_url,
            admin=admin,
            drafts=SqliteDraftStore(session_db.parent / "portal-admin.db"),
            tracker=settings.tracker_factory
            or (lambda p: tracker_from_vars(FileVarsStore(p.manifest.parent / "asac.vars.yaml"))),
            wiki=settings.wiki_factory
            or (lambda p: wiki_from_vars(FileVarsStore(p.manifest.parent / "asac.vars.yaml"))),
            forge=settings.forge_factory
            or (
                lambda p: forge_from_vars(
                    FileVarsStore(p.manifest.parent / "asac.vars.yaml"),
                    state_dir(root) / "forge-cache" / p.id,
                )
            ),
        )
    )
    app.mount("/api/v1", api)

    if (SPA_DIR / "index.html").is_file():

        @app.get("/app", include_in_schema=False)
        @app.get("/app/{path:path}", include_in_schema=False)
        def spa(path: str = "") -> Response:
            from fastapi.responses import FileResponse

            root = SPA_DIR.resolve()
            target = (root / path).resolve()
            if path and target.is_file() and target.is_relative_to(root):
                return FileResponse(target)
            # The code editor injects <style> tags; a per-request nonce allows exactly those.
            nonce = secrets.token_urlsafe(16)
            page = (
                (root / "index.html")
                .read_text(encoding="utf-8")
                .replace("<head>", f'<head><meta name="csp-nonce" content="{nonce}">', 1)
            )
            return HTMLResponse(
                page,
                headers={
                    "Content-Security-Policy": CSP.replace(
                        "style-src 'self'", f"style-src 'self' 'nonce-{nonce}'"
                    )
                },
            )  # client-side routes

    def to_spa(request: Request) -> Response:
        if (SPA_DIR / "index.html").is_file():
            return RedirectResponse("/app/", 303)
        return HTMLResponse("The web interface is not built (npm run build in web/).", 503)

    app.add_api_route("/", to_spa, methods=["GET"], include_in_schema=False)
    return app


def _inline(fn: Callable[[], None]) -> None:
    fn()


def _thread(fn: Callable[[], None]) -> None:
    import threading

    threading.Thread(target=fn, daemon=True).start()


def _now() -> str:
    from asac.clock import now_iso

    return now_iso()


def _q(text: str) -> str:
    from urllib.parse import quote

    return quote(text[:300])
