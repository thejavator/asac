"""Full OIDC login against a fake identity provider (no network, no real IdP).

The fake provider speaks the standard endpoints (discovery, authorize, token, jwks),
checks PKCE S256 for real, and signs ID tokens with a test key. Each test can break one
property (nonce, audience, expiry, signature, issuer, roles claim) to prove it is enforced.
"""

import time
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit

import httpx
import pytest
from fastapi.testclient import TestClient
from joserfc import jwt
from joserfc.jwk import RSAKey

from asac.portal.app import COOKIE, PortalSettings, create_app
from asac.portal.oidc import OidcClient, OidcConfig, OidcError, challenge
from tests.seed import seed_single

ISSUER = "https://idp.test"
CLIENT_ID = "asac-portal"
REDIRECT = "http://testserver/callback"


class FakeIdP:
    def __init__(self, signing_key: RSAKey) -> None:
        self.signing_key = signing_key
        self.codes: dict[str, dict[str, str]] = {}
        self.claims: dict[str, object] = {}  # patched into every ID token
        self.roles: object = ["product_owner"]
        self.roles_claim = "roles"
        self.refuse_token = False
        self.drop_id_token = False
        self.discovery_issuer = ISSUER
        self.http = httpx.Client(transport=httpx.MockTransport(self.handle))
        self.jwks = {"keys": [signing_key.as_dict(private=False)]}

    def handle(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/.well-known/openid-configuration":
            return httpx.Response(200, json={
                "issuer": self.discovery_issuer,
                "authorization_endpoint": f"{ISSUER}/authorize",
                "token_endpoint": f"{ISSUER}/token",
                "jwks_uri": f"{ISSUER}/jwks",
            })  # fmt: skip
        if path == "/jwks":
            return httpx.Response(200, json=self.jwks)
        if path == "/authorize":
            p = dict(request.url.params)
            if p.get("code_challenge_method") != "S256" or p.get("client_id") != CLIENT_ID:
                return httpx.Response(400, text="bad authorize request")
            code = f"code-{len(self.codes)}"
            self.codes[code] = {"challenge": p["code_challenge"], "nonce": p["nonce"]}
            loc = f"{p['redirect_uri']}?{urlencode({'code': code, 'state': p['state']})}"
            return httpx.Response(302, headers={"location": loc})
        if path == "/token":
            form = dict(parse_qsl(request.content.decode()))
            entry = self.codes.pop(form.get("code", ""), None)
            if self.refuse_token or entry is None:
                return httpx.Response(400, json={"error": "invalid_grant"})
            if challenge(form.get("code_verifier", "")) != entry["challenge"]:
                return httpx.Response(400, json={"error": "pkce_mismatch"})
            if self.drop_id_token:
                return httpx.Response(200, json={"access_token": "x"})
            now = int(time.time())
            claims: dict[str, object] = {
                "iss": ISSUER, "aud": CLIENT_ID, "sub": "alice-sub", "name": "Alice",
                "nonce": entry["nonce"], "iat": now, "exp": now + 300,
                self.roles_claim: self.roles,
            }  # fmt: skip
            claims.update(self.claims)
            token = jwt.encode({"alg": "RS256", "kid": "k1"}, claims, self.signing_key)
            return httpx.Response(200, json={"id_token": token, "token_type": "Bearer"})
        return httpx.Response(404)


@pytest.fixture(scope="module")
def keys() -> tuple[RSAKey, RSAKey]:
    return RSAKey.generate_key(2048, {"kid": "k1"}, private=True), RSAKey.generate_key(
        2048, {"kid": "k1"}, private=True
    )


@pytest.fixture
def idp(keys: tuple[RSAKey, RSAKey]) -> FakeIdP:
    return FakeIdP(keys[0])


def make_client(project: Path, idp: FakeIdP, roles_claim: str = "roles") -> TestClient:
    cfg = OidcConfig(ISSUER, CLIENT_ID, None, REDIRECT, roles_claim=roles_claim)
    settings = PortalSettings(
        data_dir=seed_single(project.parent / "portal-data", project / "asac.yaml"),
        oidc=cfg,
        harness="fake",
        secure_cookie=False,
    )
    app = create_app(settings, oidc_client=OidcClient(cfg, http=idp.http))
    return TestClient(app, follow_redirects=False)


def sign_in(client: TestClient, idp: FakeIdP) -> httpx.Response:
    """Browser flow: /login → IdP authorize → /callback with code and state."""
    r = client.get("/login")
    assert r.status_code == 303
    location = r.headers["location"]
    assert location.startswith(f"{ISSUER}/authorize")
    back = idp.http.get(location)
    assert back.status_code == 302
    parts = urlsplit(back.headers["location"])
    return client.get(f"{parts.path}?{parts.query}")


def test_authorization_request_uses_pkce_s256_state_and_nonce(
    sandbox_project: Path, idp: FakeIdP
) -> None:
    client = make_client(sandbox_project, idp)
    params = dict(parse_qsl(urlsplit(client.get("/login").headers["location"]).query))
    assert params["code_challenge_method"] == "S256"
    assert params["response_type"] == "code"
    assert len(params["state"]) >= 20 and len(params["nonce"]) >= 20
    assert params["code_challenge"] and "=" not in params["code_challenge"]


def test_happy_path_signs_in_with_roles_and_audit(sandbox_project: Path, idp: FakeIdP) -> None:
    client = make_client(sandbox_project, idp)
    r = sign_in(client, idp)
    assert r.status_code == 303 and r.headers["location"] == "/app/"
    me = client.get("/api/v1/me").json()
    assert me["name"] == "Alice" and "product_owner" in me["roles"]
    audit = client.get("/api/v1/projects/default/audit").text
    assert "Alice (alice-sub)" in audit and "portal.login" in audit


def test_roles_come_from_configured_claim(sandbox_project: Path, idp: FakeIdP) -> None:
    idp.roles_claim = "groups"
    idp.roles = ["auditor"]
    client = make_client(sandbox_project, idp, roles_claim="groups")
    sign_in(client, idp)
    assert client.get("/api/v1/projects/default/audit.csv").status_code == 200  # auditor may export


def test_unknown_roles_claim_gives_no_role(sandbox_project: Path, idp: FakeIdP) -> None:
    idp.roles = "not-a-list"  # a string claim is ignored, not split into roles
    client = make_client(sandbox_project, idp)
    sign_in(client, idp)
    assert client.get("/api/v1/me").json()["roles"] == []
    assert client.get("/api/v1/projects/default/audit.csv").status_code == 403


def test_state_mismatch_is_refused(sandbox_project: Path, idp: FakeIdP) -> None:
    client = make_client(sandbox_project, idp)
    client.get("/login")
    r = client.get("/callback?code=code-0&state=forged")
    assert r.status_code == 400 and "state mismatch" in r.text


def test_callback_without_login_is_refused(sandbox_project: Path, idp: FakeIdP) -> None:
    client = make_client(sandbox_project, idp)
    assert client.get("/callback?code=x&state=y").status_code == 400


def test_replayed_callback_is_refused(sandbox_project: Path, idp: FakeIdP) -> None:
    client = make_client(sandbox_project, idp)
    client.get("/login")
    old_cookie = client.cookies.get(COOKIE)
    sign_in_result = sign_in(client, idp)
    assert sign_in_result.status_code == 303
    # Replay the pre-login session: its login state was consumed and must not work again.
    client.cookies.set(COOKIE, old_cookie or "")
    assert client.get("/callback?code=code-0&state=x").status_code == 400


@pytest.mark.parametrize(
    "patch",
    [
        {"nonce": "someone-else"},
        {"aud": "another-client"},
        {"iss": "https://evil.example"},
        {"exp": int(time.time()) - 3600},
    ],
    ids=["nonce", "audience", "issuer", "expired"],
)
def test_invalid_id_token_claims_are_refused(
    sandbox_project: Path, idp: FakeIdP, patch: dict[str, object]
) -> None:
    idp.claims = patch
    client = make_client(sandbox_project, idp)
    r = sign_in(client, idp)
    assert r.status_code == 401 and "invalid id_token" in r.text
    assert client.get("/").status_code == 303  # still signed out


def test_token_signed_by_another_key_is_refused(
    sandbox_project: Path, idp: FakeIdP, keys: tuple[RSAKey, RSAKey]
) -> None:
    idp.signing_key = keys[1]  # the IdP's published keys do not match
    client = make_client(sandbox_project, idp)
    assert sign_in(client, idp).status_code == 401


def test_token_endpoint_refusal_and_missing_id_token(sandbox_project: Path, idp: FakeIdP) -> None:
    idp.refuse_token = True
    client = make_client(sandbox_project, idp)
    assert sign_in(client, idp).status_code == 401
    idp.refuse_token = False
    idp.drop_id_token = True
    client = make_client(sandbox_project, idp)
    assert sign_in(client, idp).status_code == 401


def test_discovery_issuer_must_match_configuration(idp: FakeIdP) -> None:
    idp.discovery_issuer = "https://other.example"
    cfg = OidcConfig(ISSUER, CLIENT_ID, None, REDIRECT)
    with pytest.raises(OidcError, match="issuer"):
        OidcClient(cfg, http=idp.http).metadata()


def test_wrong_pkce_verifier_is_refused(idp: FakeIdP) -> None:
    cfg = OidcConfig(ISSUER, CLIENT_ID, None, REDIRECT)
    idp.codes["code-x"] = {"challenge": challenge("right-verifier-" * 4), "nonce": "n"}
    with pytest.raises(OidcError, match="token endpoint refused"):
        OidcClient(cfg, http=idp.http).exchange("code-x", "wrong-verifier-" * 4, "n")


def test_logout_ends_the_session(sandbox_project: Path, idp: FakeIdP) -> None:
    client = make_client(sandbox_project, idp)
    sign_in(client, idp)
    csrf = client.get("/api/v1/me").json()["csrf"]
    assert client.post("/api/v1/logout", headers={"X-CSRF-Token": csrf}).status_code == 204
    assert client.get("/api/v1/me").status_code == 401
