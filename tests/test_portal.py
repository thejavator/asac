"""Portal security and flows, in the sandbox. Uses dev personas and a fake OIDC provider."""

import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from asac.engine.apply import create_run, execute
from asac.engine.runtime import make_context, store_for
from asac.loader.load import load_manifest
from asac.portal.app import PortalSettings, create_app
from asac.portal.oidc import Identity, challenge, new_verifier
from tests.seed import seed_single

needs_opa = pytest.mark.skipif(shutil.which("opa") is None, reason="opa binary not installed")

PERSONAS = {
    "alice": Identity("alice-sub", "Alice", frozenset({"product_owner"})),
    "carol": Identity("carol-sub", "Carol", frozenset({"auditor"})),
    "bob": Identity("bob-sub", "Bob", frozenset({"developer"})),
}


@pytest.fixture(autouse=True)
def fixed_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASAC_FIXED_TIME", "2026-01-01T00:00:00Z")


@pytest.fixture
def dev_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASAC_ENV", "dev")


def make_client(project: Path) -> TestClient:
    settings = PortalSettings(
        data_dir=seed_single(project.parent / "portal-data", project / "asac.yaml"),
        dev_personas=PERSONAS,
        harness="fake",
        secure_cookie=False,
    )
    return TestClient(create_app(settings), follow_redirects=False)


def login(client: TestClient, persona: str) -> str:
    r = client.get(f"/login?persona={persona}")
    assert r.status_code == 303
    return r.cookies.get("asac_session") or client.cookies.get("asac_session") or ""


API = "/api/v1/projects/default"


def csrf_for(client: TestClient) -> str:
    return str(client.get("/api/v1/me").json()["csrf"])


def decide(
    client: TestClient, decision: str, comment: str = "", gate: str = "gate_p1_requirements"
):  # type: ignore[no-untyped-def]
    return client.post(
        f"{API}/gates/{gate}/decision",
        json={"decision": decision, "comment": comment},
        headers={"X-CSRF-Token": csrf_for(client)},
    )


def start_run(project: Path, run_id: str = "p1") -> None:
    manifest = load_manifest(project / "asac.yaml")
    store = store_for(project / "asac.yaml", "default")
    ctx = make_context(manifest, "feature", store, project, "fake", project="default")
    create_run(ctx, run_id)
    execute(ctx, run_id)


def test_dev_personas_refused_outside_dev(sandbox_project: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("ASAC_ENV", raising=False)
    with pytest.raises(RuntimeError, match="ASAC_ENV=dev"):
        create_app(
            PortalSettings(
                data_dir=seed_single(
                    sandbox_project.parent / "portal-data", sandbox_project / "asac.yaml"
                ),
                dev_personas=PERSONAS,
            )
        )


def test_api_requires_login_and_root_redirects(sandbox_project: Path, dev_env: None) -> None:
    client = make_client(sandbox_project)
    assert client.get("/").status_code == 303
    assert client.get(f"{API}/gates").status_code == 401


def test_security_headers(sandbox_project: Path, dev_env: None) -> None:
    client = make_client(sandbox_project)
    r = client.get("/login?persona=alice")
    assert "default-src 'none'" in r.headers["content-security-policy"]
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["cache-control"] == "no-store"


def test_csrf_missing_is_refused(sandbox_project: Path, dev_env: None) -> None:
    start_run(sandbox_project)
    client = make_client(sandbox_project)
    login(client, "alice")
    r = client.post(f"{API}/gates/gate_p1_requirements/decision", json={"decision": "approve"})
    assert r.status_code == 403


@needs_opa
def test_approval_by_role_resumes_run(sandbox_project: Path, dev_env: None) -> None:
    start_run(sandbox_project)
    client = make_client(sandbox_project)
    login(client, "alice")
    r = decide(client, "approve", "ok")
    assert r.status_code == 200
    assert (
        "gate_p1_requirements approved" in r.json()["resumed"]
        or r.json()["gate"]["status"] == "approved"
    )
    gate = store_for(sandbox_project / "asac.yaml", "default").get_gate("gate_p1_requirements")
    assert gate.status == "approved" and gate.decided_by == "Alice (alice-sub)"


def test_wrong_role_refused_by_engine(sandbox_project: Path, dev_env: None) -> None:
    start_run(sandbox_project)
    client = make_client(sandbox_project)
    login(client, "bob")
    assert decide(client, "approve").status_code == 403
    gate = store_for(sandbox_project / "asac.yaml", "default").get_gate("gate_p1_requirements")
    assert gate.status == "pending"


def test_export_requires_auditor(sandbox_project: Path, dev_env: None) -> None:
    client = make_client(sandbox_project)
    login(client, "alice")
    assert client.get(f"{API}/audit.csv").status_code == 403
    client2 = make_client(sandbox_project)
    login(client2, "carol")
    r = client2.get(f"{API}/audit.csv")
    assert r.status_code == 200 and r.text.startswith("seq,at,")
    assert "attachment" in r.headers["content-disposition"]


def test_logout_needs_csrf_and_ends_session(sandbox_project: Path, dev_env: None) -> None:
    client = make_client(sandbox_project)
    login(client, "alice")
    assert client.post("/api/v1/logout").status_code == 403
    assert (
        client.post("/api/v1/logout", headers={"X-CSRF-Token": csrf_for(client)}).status_code == 204
    )
    assert client.get("/api/v1/me").status_code == 401


def test_login_rate_limited(sandbox_project: Path, dev_env: None) -> None:
    client = make_client(sandbox_project)
    codes = [client.get("/login?persona=alice").status_code for _ in range(12)]
    assert 429 in codes


def test_unknown_persona_refused(sandbox_project: Path, dev_env: None) -> None:
    client = make_client(sandbox_project)
    assert client.get("/login?persona=mallory").status_code == 400


def test_pkce_challenge_matches_rfc7636() -> None:
    # RFC 7636 appendix B test vector
    assert challenge("dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk") == (
        "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"
    )
    assert len(new_verifier()) >= 43


def test_gate_decision_audited_with_actor(sandbox_project: Path, dev_env: None) -> None:
    start_run(sandbox_project)
    client = make_client(sandbox_project)
    login(client, "alice")
    decide(client, "reject", "unclear")
    actions = [a.action for a in store_for(sandbox_project / "asac.yaml", "default").audit("p1")]
    assert "gate.rejected" in actions


def test_denied_decision_is_audited(sandbox_project: Path, dev_env: None) -> None:
    start_run(sandbox_project)
    client = make_client(sandbox_project)
    login(client, "bob")
    decide(client, "approve")
    denied = [
        a
        for a in store_for(sandbox_project / "asac.yaml", "default").audit("p1")
        if a.action == "gate.denied"
    ]
    assert len(denied) == 1
    assert denied[0].actor == "Bob (bob-sub)" and "product_owner" in denied[0].detail


def test_can_decide_is_false_without_role(sandbox_project: Path, dev_env: None) -> None:
    start_run(sandbox_project, "p1")
    client = make_client(sandbox_project)
    login(client, "bob")
    gates = client.get(f"{API}/gates").json()
    assert gates and gates[0]["can_decide"] is False


def test_reject_without_reason_is_refused(sandbox_project: Path, dev_env: None) -> None:
    start_run(sandbox_project, "p1")
    client = make_client(sandbox_project)
    login(client, "alice")
    r = decide(client, "reject", "   ")
    assert r.status_code == 409 and "needs a comment" in r.text


def test_old_server_rendered_pages_are_gone(sandbox_project: Path, dev_env: None) -> None:
    client = make_client(sandbox_project)
    login(client, "alice")
    for path in ("/gates", "/audit", "/static/portal.css"):
        assert client.get(path).status_code == 404
