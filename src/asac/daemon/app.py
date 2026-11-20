"""Webhook receiver for Jira, GitHub and GitLab issue events.

Jira and GitHub are authenticated by an HMAC of the body, GitLab by its shared token. A run
starts through the engine and never waits; ``run.triggered`` records where it came from.
"""

from __future__ import annotations

import hmac
import json
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request

from asac.clock import now_iso
from asac.daemon.triggers import (
    Event,
    parse_github,
    parse_gitlab,
    parse_jira,
    pipelines_for,
    safe_key,
    verify_signature,
)
from asac.engine.apply import create_run, execute
from asac.engine.runtime import make_context, open_store, project_root
from asac.loader.load import load_manifest
from asac.ports.state import NotFound, StateStore

SECRET_ENV = "ASAC_WEBHOOK_SECRET"


def _exists(store: StateStore, run_id: str) -> bool:
    try:
        store.get_run(run_id)
    except NotFound:
        return False
    return True


def create_app(manifest_path: Path, harness: str | None = None) -> FastAPI:
    app = FastAPI(title="ASAC daemon", docs_url=None, redoc_url=None)

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    def secret() -> str:
        value = os.environ.get(SECRET_ENV)
        if not value:
            raise HTTPException(503, f"{SECRET_ENV} is not set")
        return value

    def body_json(body: bytes) -> dict[str, Any]:
        try:
            payload = json.loads(body)
        except ValueError:
            raise HTTPException(400, "invalid JSON") from None
        return payload if isinstance(payload, dict) else {}

    def accept(ev: Event | None) -> dict[str, Any]:
        if ev is None or not safe_key(ev.key):
            return {"status": "ignored", "runs": []}
        manifest = load_manifest(manifest_path)
        runs: list[dict[str, Any]] = []
        with open_store(manifest_path) as store:
            for name in pipelines_for(manifest, ev):
                # One run per (pipeline, issue): a replayed webhook resumes, never duplicates.
                run_id = f"run_{name}_{ev.key}"
                ctx = make_context(manifest, name, store, project_root(manifest_path), harness)
                ctx.actor = "daemon"
                fresh = not _exists(store, run_id)
                create_run(ctx, run_id)
                if fresh:
                    store.append_audit(
                        run_id, "daemon", "run.triggered", now_iso(),
                        detail=f"{ev.provider}:{ev.key}:{ev.event}",
                    )  # fmt: skip
                outcome = execute(ctx, run_id)
                runs.append({"run_id": run_id, "pipeline": name, "exit": int(outcome.code)})
        return {"status": "accepted" if runs else "ignored", "runs": runs}

    @app.post("/webhooks/jira")
    async def jira(
        request: Request, x_hub_signature_256: str | None = Header(default=None)
    ) -> dict[str, Any]:
        key = secret()
        body = await request.body()
        if not verify_signature(key, body, x_hub_signature_256):
            raise HTTPException(401, "invalid signature")
        return accept(parse_jira(body_json(body)))

    @app.post("/webhooks/github")
    async def github(
        request: Request,
        x_hub_signature_256: str | None = Header(default=None),
        x_github_event: str | None = Header(default=None),
    ) -> dict[str, Any]:
        key = secret()
        body = await request.body()
        if not verify_signature(key, body, x_hub_signature_256):
            raise HTTPException(401, "invalid signature")
        return accept(parse_github(x_github_event, body_json(body)))

    @app.post("/webhooks/gitlab")
    async def gitlab(
        request: Request, x_gitlab_token: str | None = Header(default=None)
    ) -> dict[str, Any]:
        # GitLab sends the shared secret itself, not an HMAC: compare in constant time.
        if not hmac.compare_digest(secret().encode(), (x_gitlab_token or "").encode()):
            raise HTTPException(401, "invalid token")
        return accept(parse_gitlab(body_json(await request.body())))

    return app
