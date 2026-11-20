"""JSON API /api/v1: problem+json errors, CSRF, role x endpoint matrix, project isolation."""

import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from asac.engine.apply import create_run, execute
from asac.engine.runtime import make_context, open_store
from asac.loader.load import load_manifest
from asac.portal.app import PortalSettings, create_app
from asac.portal.oidc import Identity
from tests.seed import seed_portal

needs_opa = pytest.mark.skipif(shutil.which("opa") is None, reason="opa binary not installed")

PERSONAS = {
    "alice": Identity("alice-sub", "Alice", frozenset({"payments-team", "payments-po"})),
    "bob": Identity("bob-sub", "Bob", frozenset({"payments-team"})),
    "carol": Identity("carol-sub", "Carol", frozenset({"auditor"})),
    "dave": Identity("dave-sub", "Dave", frozenset({"billing-team"})),
    "erin": Identity("erin-sub", "Erin", frozenset({"admin"})),
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


def start_run(manifest: Path, project: str, run_id: str = "p1") -> None:
    m = load_manifest(manifest)
    with open_store(manifest, project) as store:
        ctx = make_context(m, "feature", store, manifest.parent, "fake", project=project)
        create_run(ctx, run_id)
        execute(ctx, run_id)


def client_for(file: Path, persona: str | None = None) -> TestClient:
    settings = PortalSettings(
        data_dir=seed_portal(file), dev_personas=PERSONAS, harness="fake", secure_cookie=False
    )
    c = TestClient(create_app(settings), follow_redirects=False)
    if persona:
        assert c.get(f"/login?persona={persona}").status_code == 303
    return c


def csrf(c: TestClient) -> str:
    return str(c.get("/api/v1/me").json()["csrf"])


def test_unauthenticated_gets_problem_json(org: Path) -> None:
    c = client_for(org)
    r = c.get("/api/v1/projects")
    assert r.status_code == 401
    assert r.headers["content-type"].startswith("application/problem+json")
    assert r.json() == {"type": "about:blank", "title": "Authentication required", "status": 401}


def test_openapi_is_published(org: Path) -> None:
    doc = client_for(org).get("/api/v1/openapi.json").json()
    ops = {op["operationId"] for path in doc["paths"].values() for op in path.values()}
    assert {"getMe", "listProjects", "listRuns", "getRun", "listGates", "decideGate"} <= ops


def test_csp_allows_same_origin_scripts_only(org: Path) -> None:
    r = client_for(org, "alice").get("/api/v1/me")
    csp = r.headers["content-security-policy"]
    assert "script-src 'self'" in csp and "connect-src 'self'" in csp
    assert "unsafe-inline" not in csp and "unsafe-eval" not in csp


def test_me(org: Path) -> None:
    body = client_for(org, "alice").get("/api/v1/me").json()
    assert body["sub"] == "alice-sub" and body["organization"] == "Acme"
    assert body["roles"] == ["payments-po", "payments-team"] and body["csrf"]


def test_projects_visibility_and_roles(org: Path) -> None:
    alice = client_for(org, "alice").get("/api/v1/projects").json()
    assert [p["id"] for p in alice] == ["payments"]
    assert "product_owner" in alice[0]["roles"]
    carol = client_for(org, "carol").get("/api/v1/projects").json()
    assert [p["id"] for p in carol] == ["payments", "billing"]


# persona, endpoint (payments project), expected status
MATRIX = [
    ("alice", "/api/v1/projects/payments/runs", 200),
    ("bob", "/api/v1/projects/payments/runs", 200),
    ("carol", "/api/v1/projects/payments/runs", 200),
    ("dave", "/api/v1/projects/payments/runs", 404),
    ("dave", "/api/v1/projects/payments/runs/p1", 404),
    ("dave", "/api/v1/projects/payments/gates", 404),
    ("dave", "/api/v1/projects/payments/audit", 404),
    ("dave", "/api/v1/projects/payments/pipelines", 404),
    ("alice", "/api/v1/projects/payments/runs/p1", 200),
    ("alice", "/api/v1/projects/payments/runs/nope", 404),
    ("alice", "/api/v1/projects/nope/runs", 404),
    ("carol", "/api/v1/projects/payments/audit", 200),
    ("bob", "/api/v1/projects/payments/pipelines", 200),
]


@pytest.mark.parametrize(("persona", "path", "expected"), MATRIX)
def test_role_endpoint_matrix(org: Path, persona: str, path: str, expected: int) -> None:
    start_run(org.parent / "payments/asac.yaml", "payments")
    r = client_for(org, persona).get(path)
    assert r.status_code == expected, r.text
    if expected >= 400:
        assert r.headers["content-type"].startswith("application/problem+json")


def test_run_detail_content(org: Path) -> None:
    start_run(org.parent / "payments/asac.yaml", "payments")
    body = client_for(org, "alice").get("/api/v1/projects/payments/runs/p1").json()
    assert body["run"]["status"] == "gate_waiting"
    assert body["run"]["steps"][0]["id"] == "requirements"
    gate = body["gates"][0]
    assert gate["gate_id"] == "gate_p1_requirements" and gate["can_decide"] is True
    assert any(a["action"].startswith("run.") for a in body["audit"])


def test_can_decide_reflects_role(org: Path) -> None:
    start_run(org.parent / "payments/asac.yaml", "payments")
    gates = client_for(org, "bob").get("/api/v1/projects/payments/gates").json()
    assert gates and gates[0]["can_decide"] is False


def test_decision_requires_csrf_header(org: Path) -> None:
    start_run(org.parent / "payments/asac.yaml", "payments")
    c = client_for(org, "alice")
    r = c.post(
        "/api/v1/projects/payments/gates/gate_p1_requirements/decision",
        json={"decision": "approve"},
    )
    assert r.status_code == 403 and r.json()["detail"] == "invalid CSRF token"


def test_wrong_role_refused_and_audited(org: Path) -> None:
    start_run(org.parent / "payments/asac.yaml", "payments")
    c = client_for(org, "bob")
    r = c.post(
        "/api/v1/projects/payments/gates/gate_p1_requirements/decision",
        json={"decision": "approve"},
        headers={"X-CSRF-Token": csrf(c)},
    )
    assert r.status_code == 403
    with open_store(org.parent / "payments/asac.yaml", "payments") as store:
        assert any(a.action == "gate.denied" for a in store.audit(None))


def test_audit_problems_filter_keeps_only_errors(org: Path) -> None:
    start_run(org.parent / "payments/asac.yaml", "payments")
    c = client_for(org, "bob")
    c.post(
        "/api/v1/projects/payments/gates/gate_p1_requirements/decision",
        json={"decision": "approve"},
        headers={"X-CSRF-Token": csrf(c)},
    )
    everything = c.get("/api/v1/projects/payments/audit").json()["items"]
    problems = c.get("/api/v1/projects/payments/audit?problems=true").json()["items"]
    assert [a["action"] for a in problems] == ["gate.denied"]
    assert len(everything) > len(problems)


def test_decisions_cover_every_project_and_filter_mine(org: Path) -> None:
    start_run(org.parent / "payments/asac.yaml", "payments")
    alice = client_for(org, "alice")  # product_owner: may sign
    bob = client_for(org, "bob")
    everything = bob.get("/api/v1/decisions").json()
    assert [g["gate_id"] for g in everything] == ["gate_p1_requirements"]
    assert everything[0]["project_id"] == "payments" and not everything[0]["can_decide"]
    assert bob.get("/api/v1/decisions?mine=true").json() == []
    mine = alice.get("/api/v1/decisions?mine=true").json()
    assert mine[0]["can_decide"] and mine[0]["project_name"]
    assert alice.get("/api/v1/decisions?project=other").json() == []
    assert client_for(org).get("/api/v1/decisions").status_code == 401


def test_reject_needs_comment(org: Path) -> None:
    start_run(org.parent / "payments/asac.yaml", "payments")
    c = client_for(org, "alice")
    r = c.post(
        "/api/v1/projects/payments/gates/gate_p1_requirements/decision",
        json={"decision": "reject"},
        headers={"X-CSRF-Token": csrf(c)},
    )
    assert r.status_code == 409


def test_invalid_body_is_problem(org: Path) -> None:
    c = client_for(org, "alice")
    r = c.post(
        "/api/v1/projects/payments/gates/x/decision",
        json={"decision": "maybe"},
        headers={"X-CSRF-Token": csrf(c)},
    )
    assert r.status_code == 422
    assert r.headers["content-type"].startswith("application/problem+json")


@needs_opa
def test_approval_resumes(org: Path) -> None:
    start_run(org.parent / "payments/asac.yaml", "payments")
    c = client_for(org, "alice")
    r = c.post(
        "/api/v1/projects/payments/gates/gate_p1_requirements/decision",
        json={"decision": "approve", "comment": "ok"},
        headers={"X-CSRF-Token": csrf(c)},
    )
    assert r.status_code == 200, r.text
    assert r.json()["gate"]["status"] == "approved"


def test_runs_cursor_pagination(org: Path) -> None:
    manifest = org.parent / "payments/asac.yaml"
    for i in range(3):
        start_run(manifest, "payments", f"r{i}")
    c = client_for(org, "alice")
    first = c.get("/api/v1/projects/payments/runs?limit=2").json()
    assert len(first["items"]) == 2 and first["next_cursor"]
    second = c.get(f"/api/v1/projects/payments/runs?limit=2&cursor={first['next_cursor']}").json()
    assert len(second["items"]) == 1 and second["next_cursor"] is None
    ids = {r["run_id"] for r in first["items"] + second["items"]}
    assert ids == {"r0", "r1", "r2"}
    assert c.get("/api/v1/projects/payments/runs?cursor=!!").status_code == 400


def test_pipelines_shape(org: Path) -> None:
    body = client_for(org, "bob").get("/api/v1/projects/payments/pipelines").json()
    feature = next(p for p in body if p["name"] == "feature")
    first = feature["steps"][0]
    assert first["id"] == "requirements" and first["gate_role"] == "product_owner"


def test_states_are_isolated_between_projects(org: Path) -> None:
    start_run(org.parent / "payments/asac.yaml", "payments")
    dave = client_for(org, "dave").get("/api/v1/projects/billing/runs").json()
    assert dave["items"] == []


def test_variables_read_requires_visibility(org: Path) -> None:
    assert client_for(org, "dave").get("/api/v1/projects/payments/variables").status_code == 404
    got = client_for(org, "bob").get("/api/v1/projects/payments/variables")
    assert got.status_code == 200


def test_variables_write_needs_owner_and_csrf(org: Path) -> None:
    url = "/api/v1/projects/payments/variables/jira_url"
    bob = client_for(org, "bob")
    r = bob.put(url, json={"value": "https://j.example.com"}, headers={"X-CSRF-Token": csrf(bob)})
    assert r.status_code == 403
    carol = client_for(org, "carol")  # auditor reads everything, never writes
    assert (
        carol.put(
            url, json={"value": "https://j"}, headers={"X-CSRF-Token": csrf(carol)}
        ).status_code
        == 403
    )
    erin = client_for(org, "erin")  # org admin
    assert erin.put(url, json={"value": "https://j"}).status_code == 403  # no CSRF
    ok = erin.put(
        url, json={"value": "https://j.example.com"}, headers={"X-CSRF-Token": csrf(erin)}
    )
    assert ok.status_code == 200 and ok.json()["secret"] is False
    with open_store(org.parent / "payments/asac.yaml", "payments") as store:
        assert any(a.action == "variable.set" for a in store.audit(None))


def test_literal_secret_is_refused_and_not_echoed(org: Path) -> None:
    carol = client_for(org, "erin")
    r = carol.put(
        "/api/v1/projects/payments/variables/gitlab_token",
        json={"value": "glpat-SUPERSECRET"},
        headers={"X-CSRF-Token": csrf(carol)},
    )
    assert r.status_code == 422 and "SUPERSECRET" not in r.text
    ref = carol.put(
        "/api/v1/projects/payments/variables/gitlab_token",
        json={"value": "${vault.gitlab/token}"},
        headers={"X-CSRF-Token": csrf(carol)},
    )
    assert ref.status_code == 200 and ref.json()["secret"] is True


def test_probe_refuses_private_addresses() -> None:
    from asac.portal.probe import probe_url

    assert probe_url("http://127.0.0.1:9/")[0] is False
    assert probe_url("ftp://example.com")[0] is False


def test_spa_deep_links_serve_index_and_refuse_traversal(org: Path) -> None:
    from asac.portal.app import SPA_DIR

    if not (SPA_DIR / "index.html").is_file():
        pytest.skip("SPA not built (npm run build in web/)")
    c = client_for(org)
    assert "root" in c.get("/app/p/payments/runs/r1").text
    assert c.get("/app/%2e%2e/app.py").headers["content-type"].startswith("text/html")


def test_spa_index_nonce_is_per_request_and_scoped_to_styles(org: Path) -> None:
    from asac.portal.app import SPA_DIR

    if not (SPA_DIR / "index.html").is_file():
        pytest.skip("SPA not built (npm run build in web/)")
    c = client_for(org)
    a, b = c.get("/app/"), c.get("/app/p/payments/runs")
    na = a.headers["content-security-policy"].split("'nonce-")[1].split("'")[0]
    nb = b.headers["content-security-policy"].split("'nonce-")[1].split("'")[0]
    assert na != nb and f'content="{na}"' in a.text
    csp = a.headers["content-security-policy"]
    assert "script-src 'self';" in csp and "unsafe-inline" not in csp


def test_admin_endpoints_need_admin_role(org: Path) -> None:
    for who in ("alice", "carol"):
        assert client_for(org, who).get("/api/v1/admin/users").status_code == 403
    erin = client_for(org, "erin")
    names = [u["name"] for u in erin.get("/api/v1/admin/users").json()]
    assert "Erin" in names


def test_mapping_grants_visibility_and_role_and_is_audited(org: Path) -> None:
    url = "/api/v1/projects/billing/mappings"
    erin = client_for(org, "erin")
    r = erin.post(
        url, json={"claim": "payments-team", "role": "qa"}, headers={"X-CSRF-Token": csrf(erin)}
    )
    assert r.status_code == 201
    bob = client_for(org, "bob")  # in payments-team only; now sees billing with the qa role
    projects = {p["id"]: p for p in bob.get("/api/v1/projects").json()}
    assert "qa" in projects["billing"]["roles"]
    dup = erin.post(
        url, json={"claim": "payments-team", "role": "qa"}, headers={"X-CSRF-Token": csrf(erin)}
    )
    assert dup.status_code == 409
    events = erin.get("/api/v1/admin/events").json()
    assert events[0]["action"] == "mapping.added"
    gone = erin.delete(f"{url}/payments-team/qa", headers={"X-CSRF-Token": csrf(erin)})
    assert gone.status_code == 204
    assert "billing" not in {p["id"] for p in client_for(org, "bob").get("/api/v1/projects").json()}


def test_mapping_changes_need_owner_or_admin_and_csrf(org: Path) -> None:
    url = "/api/v1/projects/payments/mappings"
    body = {"claim": "x", "role": "reader"}
    bob = client_for(org, "bob")
    assert bob.post(url, json=body, headers={"X-CSRF-Token": csrf(bob)}).status_code == 403
    erin = client_for(org, "erin")
    assert erin.post(url, json=body).status_code == 403  # no CSRF
    bad = erin.post(url, json={"claim": "x", "role": "root"}, headers={"X-CSRF-Token": csrf(erin)})
    assert bad.status_code == 422


def test_run_detail_shows_trigger_with_ticket_link_and_wiki_search(org: Path) -> None:
    import httpx

    from asac.adapters.tracker_http import Jira
    from asac.adapters.wiki_http import Confluence
    from tests.conformance import fake_trackers as fk

    manifest = org.parent / "payments/asac.yaml"
    start_run(manifest, "payments", "run_feature_PAY-139")
    with open_store(manifest, "payments") as store:
        store.append_audit(
            "run_feature_PAY-139", "daemon", "run.triggered", "2026-01-01T00:00:00Z",
            detail="jira:PAY-139:issue_created",
        )  # fmt: skip
    cl = lambda t: httpx.Client(transport=t)  # noqa: E731
    settings = PortalSettings(
        data_dir=seed_portal(org), dev_personas=PERSONAS, harness="fake", secure_cookie=False,
        tracker_factory=lambda _p: Jira("https://j.test", "t", None, cl(fk.jira())),
        wiki_factory=lambda _p: Confluence("https://c.test/wiki", "PAY", "t", None, cl(fk.confluence())),  # noqa: E501
    )  # fmt: skip
    c = TestClient(create_app(settings), follow_redirects=False)
    assert c.get("/login?persona=bob").status_code == 303
    body = c.get("/api/v1/projects/payments/runs/run_feature_PAY-139").json()
    assert body["trigger"] == {
        "provider": "jira", "event": "issue_created", "key": "PAY-139",
        "label": "PAY-139 in Jira", "url": "https://j.test/browse/PAY-139",
        "title": "Split refund and chargeback flows", "status": "In Progress",
    }  # fmt: skip
    pages = c.get("/api/v1/projects/payments/wiki/pages?q=refund").json()
    assert pages[0]["title"] == "Refund policy"
    dave = client_for(org, "dave")
    assert dave.get("/api/v1/projects/payments/wiki/pages?q=x").status_code == 404


def test_run_without_trigger_or_tracker_degrades_to_plain_label(org: Path) -> None:
    manifest = org.parent / "payments/asac.yaml"
    start_run(manifest, "payments", "p2")
    c = client_for(org, "bob")
    assert c.get("/api/v1/projects/payments/runs/p2").json()["trigger"] is None
    assert c.get("/api/v1/projects/payments/wiki/pages?q=x").status_code == 409
    with open_store(manifest, "payments") as store:
        store.append_audit("p2", "daemon", "run.triggered", "2026-01-01T00:00:00Z", detail="jira:PAY-1:issue_created")  # fmt: skip  # noqa: E501
    t = c.get("/api/v1/projects/payments/runs/p2").json()["trigger"]
    assert t["label"] == "PAY-1 in Jira" and t["url"] is None


def test_run_detail_lists_artifacts_spend_and_downloads_safely(org: Path) -> None:
    from asac.adapters import state_dir
    from asac.adapters.artifacts_fs import FsArtifactStore

    manifest = org.parent / "payments/asac.yaml"
    start_run(manifest, "payments", "p3")
    store = FsArtifactStore(state_dir(manifest.parent, "payments") / "artifacts")
    store.put("p3", "requirements", "spec.md", b"# spec\n", "2026-01-01T00:00:00Z")
    c = client_for(org, "bob")
    body = c.get("/api/v1/projects/payments/runs/p3").json()
    assert body["artifacts"][0]["name"] == "spec.md" and body["spend"]["tokens"] > 0
    r = c.get("/api/v1/projects/payments/runs/p3/artifacts/spec.md")
    assert r.status_code == 200 and r.content == b"# spec\n"
    assert "attachment" in r.headers["content-disposition"]
    assert c.get("/api/v1/projects/payments/runs/p3/artifacts/nope.md").status_code == 404
    traversal = "/api/v1/projects/payments/runs/p3/artifacts/..%2Findex.jsonl"
    assert c.get(traversal).status_code == 404
    assert (
        client_for(org, "dave")
        .get("/api/v1/projects/payments/runs/p3/artifacts/spec.md")
        .status_code
        == 404
    )


def test_login_options_are_public_and_list_dev_personas(org: Path) -> None:
    body = client_for(org).get("/api/v1/login-options").json()  # no session
    assert body["mode"] == "dev" and body["organization"] == "Acme"
    assert {p["id"] for p in body["personas"]} == set(PERSONAS)
    assert "sub" not in str(body) and "csrf" not in body


def test_login_without_persona_goes_to_the_sign_in_screen(org: Path) -> None:
    r = client_for(org).get("/login")
    assert r.status_code == 303 and r.headers["location"] == "/app/"


# --- project administration (database) -------------------------------------------------------


def _admin(org: Path) -> tuple[TestClient, dict[str, str]]:
    c = client_for(org, "erin")
    return c, {"X-CSRF-Token": csrf(c)}


def test_project_admin_requires_admin_and_csrf(org: Path) -> None:
    body = {"id": "new", "name": "New", "manifest": str(org.parent / "payments/asac.yaml")}
    bob = client_for(org, "bob")
    assert bob.get("/api/v1/admin/projects").status_code == 403
    assert (
        bob.post(
            "/api/v1/admin/projects", json=body, headers={"X-CSRF-Token": csrf(bob)}
        ).status_code
        == 403
    )
    erin, h = _admin(org)
    assert erin.post("/api/v1/admin/projects", json=body).status_code == 403  # no CSRF header
    assert erin.post("/api/v1/admin/projects", json=body, headers=h).status_code == 201


def test_create_update_archive_restore_are_audited(org: Path) -> None:
    c, h = _admin(org)
    manifest = str(org.parent / "payments/asac.yaml")
    body = {"id": "new", "name": "New", "manifest": manifest, "access": ["new-team"]}
    assert c.post("/api/v1/admin/projects", json=body, headers=h).status_code == 201
    assert c.post("/api/v1/admin/projects", json=body, headers=h).status_code == 409
    bad = {**body, "id": "Bad Id"}
    assert c.post("/api/v1/admin/projects", json=bad, headers=h).status_code == 422
    missing = {**body, "id": "m2", "manifest": "/nope/asac.yaml"}
    assert c.post("/api/v1/admin/projects", json=missing, headers=h).status_code == 422
    relative = {**body, "id": "m3", "manifest": "asac.yaml"}
    assert c.post("/api/v1/admin/projects", json=relative, headers=h).status_code == 422
    upd = {"name": "Renamed", "manifest": manifest, "access": []}
    assert c.put("/api/v1/admin/projects/new", json=upd, headers=h).json()["name"] == "Renamed"
    assert c.put("/api/v1/admin/projects/nope", json=upd, headers=h).status_code == 404
    assert c.post("/api/v1/admin/projects/new/archive", headers=h).status_code == 204
    listed = {p["id"]: p for p in c.get("/api/v1/admin/projects").json()}
    assert listed["new"]["archived"] is True
    assert "new" not in [p["id"] for p in c.get("/api/v1/projects").json()]
    assert c.post("/api/v1/admin/projects/new/restore", headers=h).status_code == 204
    actions = [e["action"] for e in c.get("/api/v1/admin/events").json()]
    assert {"project.created", "project.updated", "project.archived", "project.restored"} <= set(
        actions
    )


def test_organization_is_editable_by_admin(org: Path) -> None:
    c, h = _admin(org)
    r = c.put(
        "/api/v1/admin/organization", json={"name": "Globex", "org_roles": ["auditor"]}, headers=h
    )
    assert r.status_code == 200
    assert c.get("/api/v1/admin/organization").json()["name"] == "Globex"
    assert c.get("/api/v1/me").json()["organization"] == "Globex"
    assert client_for(org, "bob").put(
        "/api/v1/admin/organization", json={"name": "x"}
    ).status_code in (403,)


def inline_client(file: Path, persona: str) -> TestClient:
    settings = PortalSettings(
        data_dir=seed_portal(file), dev_personas=PERSONAS, harness="fake",
        secure_cookie=False, run_inline=True,
    )  # fmt: skip
    c = TestClient(create_app(settings), follow_redirects=False)
    assert c.get(f"/login?persona={persona}").status_code == 303
    return c


def test_plan_shows_steps_and_estimate(org: Path) -> None:
    c = client_for(org, "bob")
    body = c.get("/api/v1/projects/payments/pipelines/feature/plan").json()
    assert body["steps"] and body["estimated_tokens"] > 0 and body["over_budget"] is False
    assert c.get("/api/v1/projects/payments/pipelines/nope/plan").status_code == 404


def test_start_run_creates_and_executes_it(org: Path) -> None:
    c = inline_client(org, "alice")
    r = c.post(
        "/api/v1/projects/payments/runs", json={"pipeline": "feature"},
        headers={"X-CSRF-Token": csrf(c)},
    )  # fmt: skip
    assert r.status_code == 202
    run_id = r.json()["run_id"]
    run = c.get(f"/api/v1/projects/payments/runs/{run_id}").json()
    assert run["run"]["status"] == "gate_waiting"  # ran up to the first gate
    assert any(a["action"] == "run.created" for a in run["audit"])


def test_start_run_needs_csrf_role_and_a_known_pipeline(org: Path) -> None:
    alice, bob = inline_client(org, "alice"), inline_client(org, "bob")
    url = "/api/v1/projects/payments/runs"
    assert alice.post(url, json={"pipeline": "feature"}).status_code == 403  # no CSRF
    assert (
        bob.post(url, json={"pipeline": "feature"}, headers={"X-CSRF-Token": csrf(bob)}).status_code
        == 403
    )
    r = alice.post(url, json={"pipeline": "nope"}, headers={"X-CSRF-Token": csrf(alice)})
    assert r.status_code == 404


def test_stop_run_marks_it_killed_and_audits(org: Path) -> None:
    c = inline_client(org, "alice")
    h = {"X-CSRF-Token": csrf(c)}
    run_id = c.post(
        "/api/v1/projects/payments/runs", json={"pipeline": "feature"}, headers=h
    ).json()["run_id"]
    assert c.post(f"/api/v1/projects/payments/runs/{run_id}/stop", headers=h).status_code == 204
    run = c.get(f"/api/v1/projects/payments/runs/{run_id}").json()
    assert run["run"]["status"] == "killed"
    assert any(a["action"] == "run.killed" for a in run["audit"])
    assert c.post(f"/api/v1/projects/payments/runs/{run_id}/stop", headers=h).status_code == 409
