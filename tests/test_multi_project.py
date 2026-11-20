"""Multi-project portal: registry file, visibility, role mapping, state isolation."""

import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from asac.adapters.projects_sqlite import SqliteProjectRegistry
from asac.engine.apply import create_run, execute
from asac.engine.runtime import make_context, open_store
from asac.loader.load import load_manifest
from asac.portal.app import PortalSettings, create_app
from asac.portal.oidc import Identity
from tests.seed import seed_portal

needs_opa = pytest.mark.skipif(shutil.which("opa") is None, reason="opa binary not installed")

PERSONAS = {
    "alice": Identity("alice-sub", "Alice", frozenset({"payments-team", "payments-po"})),
    "bob": Identity("bob-sub", "Bob", frozenset({"billing-team"})),
    "carol": Identity("carol-sub", "Carol", frozenset({"auditor"})),
}

FILE = """
organization: Acme
org_roles: [auditor]
projects:
  - id: payments
    name: Payments
    manifest: payments/asac.yaml
    access: [payments-team]
    roles: {payments-po: [product_owner]}
  - id: billing
    name: Billing
    manifest: billing/asac.yaml
    access: [billing-team]
"""


@pytest.fixture(autouse=True)
def env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ASAC_ENV", "dev")
    monkeypatch.setenv("ASAC_FIXED_TIME", "2026-01-01T00:00:00Z")
    monkeypatch.setenv("ASAC_STATE_DIR", str(tmp_path / "state"))


@pytest.fixture
def org(sandbox_project: Path, tmp_path: Path) -> Path:
    root = tmp_path / "org"
    for name in ("payments", "billing"):
        shutil.copytree(sandbox_project, root / name)
    (root / "portal-seed.yaml").write_text(FILE)
    return root / "portal-seed.yaml"


def client(file: Path) -> TestClient:
    settings = PortalSettings(
        data_dir=seed_portal(file), dev_personas=PERSONAS, harness="fake", secure_cookie=False
    )
    return TestClient(create_app(settings), follow_redirects=False)


def test_registry_keeps_absolute_manifest_and_order(org: Path) -> None:
    d = SqliteProjectRegistry(seed_portal(org) / "portal-admin.db").load()
    assert [p.id for p in d.projects] == ["payments", "billing"]
    assert d.projects[0].manifest == (org.parent / "payments/asac.yaml").resolve()


def test_visibility_and_org_roles(org: Path) -> None:
    c = client(org)
    c.get("/login?persona=alice")
    assert c.get("/api/v1/projects/payments/runs").status_code == 200
    assert c.get("/api/v1/projects/billing/runs").status_code == 404
    assert c.get("/api/v1/projects/nope/runs").status_code == 404
    c2 = client(org)
    c2.get("/login?persona=carol")
    assert c2.get("/api/v1/projects/payments/runs").status_code == 200
    assert c2.get("/api/v1/projects/billing/runs").status_code == 200
    assert {p["name"] for p in c2.get("/api/v1/projects").json()} == {"Payments", "Billing"}


def test_project_list_only_shows_visible(org: Path) -> None:
    c = client(org)
    c.get("/login?persona=bob")
    assert [p["name"] for p in c.get("/api/v1/projects").json()] == ["Billing"]


@needs_opa
def test_state_is_isolated_per_project(org: Path) -> None:
    d = SqliteProjectRegistry(seed_portal(org) / "portal-admin.db").load()
    pay = d.projects[0]
    manifest = load_manifest(pay.manifest)
    with open_store(pay.manifest, "payments") as store:
        ctx = make_context(
            manifest, "feature", store, pay.manifest.parent, "fake", project="payments"
        )
        create_run(ctx, "r1")
        execute(ctx, "r1")
    with open_store(d.projects[1].manifest, "billing") as store:
        assert store.list_runs() == []
    with open_store(pay.manifest, "payments") as store:
        assert [r.run_id for r in store.list_runs()] == ["r1"]


def test_unauthenticated_refused(org: Path) -> None:
    assert client(org).get("/api/v1/projects/payments/runs").status_code == 401
    assert client(org).get("/").status_code == 303
