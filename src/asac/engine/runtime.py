"""Glue between the CLI and the engine: builds a context from a manifest path."""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from typing import Any

from asac.adapters import AdapterContext, harness_factory, open_state, state_dir
from asac.adapters.artifacts_fs import FsArtifactStore
from asac.adapters.notify import from_project
from asac.adapters.opa_policy import OpaPolicyEngine
from asac.adapters.runner_local import runner_from_vars
from asac.engine.apply import Context
from asac.engine.workspace import create_workspace
from asac.loader.load import load_manifest, load_vars
from asac.model import Manifest
from asac.ports.harness import Harness
from asac.ports.runner import Runner
from asac.ports.state import StateError, StateStore


def project_root(manifest_path: Path) -> Path:
    return manifest_path.resolve().parent


def load(manifest_path: Path) -> Manifest:
    return load_manifest(manifest_path)


def _vars(root: Path) -> dict[str, Any]:
    path = root / "asac.vars.yaml"
    return load_vars(path).values if path.is_file() else {}


def resolve_harness_name(value: str, values: dict[str, Any]) -> str:
    """``var.x`` is looked up in layer 2; anything else is the harness id itself."""
    if value.startswith("var."):
        key = value[4:]
        if key not in values:
            raise StateError(f"harness variable '{value}' is not set in asac.vars.yaml")
        return str(values[key])
    return value


def _flag(env: str | None, default: bool) -> bool:
    """The environment variable, when set, overrides the vars file (1/true/yes or 0/false/no)."""
    if env is None or env == "":
        return default
    return env.lower() in ("1", "true", "yes")


def _retries(values: dict[str, Any]) -> int:
    """``retries`` (vars file) or ``ASAC_RETRIES``: extra attempts per failed step, capped at 5."""
    raw = os.environ.get("ASAC_RETRIES", values.get("retries", 0))
    try:
        return max(0, min(5, int(raw)))
    except (TypeError, ValueError):
        return 0


def _parallel(values: dict[str, Any]) -> int:
    """``parallel`` (vars file) or ``ASAC_PARALLEL``: steps run together per wave, 1 to 8."""
    raw = os.environ.get("ASAC_PARALLEL", values.get("parallel", 1))
    try:
        return max(1, min(8, int(raw)))
    except (TypeError, ValueError):
        return 1


def make_context(
    manifest: Manifest,
    pipeline: str,
    store: StateStore,
    root: Path,
    harness_name: str | None = None,
    runner: Runner | None = None,
    project: str | None = None,
) -> Context:
    values = _vars(root)
    sdir = state_dir(root, project)
    isolated = _isolation(harness_name, values)

    def workspace(run_id: str) -> tuple[Path, str, str] | None:
        # The worktree is created with the run; its path and base sha go to the audit.
        if not isolated:
            return None
        ws = create_workspace(root, sdir, run_id)
        return ws.path, ws.branch, ws.base

    adapter_ctx = AdapterContext(
        root=root,
        manifest=manifest,
        state_dir=sdir,
        autorun=_flag(os.environ.get("ASAC_AUTORUN"), bool(values.get("autorun", False))),
        autorun_timeout=int(
            os.environ.get("ASAC_AUTORUN_TIMEOUT", values.get("autorun_timeout", 900))
        ),
    )
    # One harness per (run, harness): mounted skills accumulate within a run, and a
    # context shared by several runs (daemon, portal) never writes into another run's tree.
    cache: dict[tuple[str, str], Harness] = {}

    def harness_for(agent: str, run_id: str = "") -> Harness:
        name = harness_name or resolve_harness_name(manifest.agents[agent].harness, values)
        key = (run_id, name)
        if key not in cache:
            work = recorded_workspace(store, run_id) if isolated and run_id else None
            cache[key] = harness_factory(name, replace(adapter_ctx, work=work))
        return cache[key]

    return Context(
        manifest=manifest,
        pipeline_name=pipeline,
        store=store,
        harness_for=harness_for,
        root=root,
        policy_engine=OpaPolicyEngine(root),
        runner=runner if runner is not None else runner_from_vars(root, values),
        notifier=from_project(values, dict(os.environ)),
        artifacts=FsArtifactStore(sdir / "artifacts"),
        retries=_retries(values),
        parallel=_parallel(values),
        workspace=workspace if isolated else None,
        workdir_for=(lambda rid: recorded_workspace(store, rid)) if isolated else None,
    )


def recorded_workspace(store: StateStore, run_id: str) -> Path | None:
    """The worktree of a run, as recorded by ``workspace.created`` (the source of truth)."""
    for a in store.audit(run_id):
        if a.action == "workspace.created":
            fields = dict(p.split("=", 1) for p in a.detail.split() if "=" in p)
            if "path" in fields:
                path = Path(fields["path"])
                if not path.is_dir():
                    raise StateError(f"the worktree of run '{run_id}' is missing ({path})")
                return path
    return None


def _isolation(harness_name: str | None, values: dict[str, Any]) -> bool:
    """Isolation is on for the real tools. ``ASAC_ISOLATE=0|1`` or ``isolate:`` overrides."""
    env = os.environ.get("ASAC_ISOLATE")
    if env is not None and env != "":
        return env.lower() in ("1", "true", "yes")
    if "isolate" in values:
        return bool(values["isolate"])
    return harness_name != "fake"


def store_for(manifest_path: Path, project: str | None = None) -> StateStore:
    return open_state(project_root(manifest_path), project)


@contextmanager
def open_store(manifest_path: Path, project: str | None = None) -> Iterator[StateStore]:
    """A store that is closed when the request or command is done (no leaked connections)."""
    store = store_for(manifest_path, project)
    try:
        yield store
    finally:
        close = getattr(store, "close", None)
        if callable(close):
            close()


__all__ = [
    "load",
    "make_context",
    "open_store",
    "project_root",
    "resolve_harness_name",
    "store_for",
]
