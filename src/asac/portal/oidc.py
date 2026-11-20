"""Minimal OIDC relying party: authorization code flow with PKCE, ID token validation.

Works with any standard provider (Keycloak, Entra, Okta). Nothing here is vendor specific.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx
from joserfc import jwt
from joserfc.errors import JoseError
from joserfc.jwk import KeySet


class OidcError(Exception):
    pass


@dataclass(frozen=True)
class OidcConfig:
    issuer: str
    client_id: str
    client_secret: str | None
    redirect_uri: str
    roles_claim: str = "roles"
    scopes: str = "openid profile email"


@dataclass(frozen=True)
class Identity:
    subject: str
    name: str
    roles: frozenset[str]


def new_verifier() -> str:
    return secrets.token_urlsafe(64)


def challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return str(base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii"))


class OidcClient:
    def __init__(self, cfg: OidcConfig, http: httpx.Client | None = None) -> None:
        self.cfg = cfg
        self.http = http or httpx.Client(timeout=10)
        self._meta: dict[str, Any] | None = None
        self._keys: KeySet | None = None

    def metadata(self) -> dict[str, Any]:
        if self._meta is None:
            url = self.cfg.issuer.rstrip("/") + "/.well-known/openid-configuration"
            meta = self.http.get(url).raise_for_status().json()
            if meta.get("issuer") != self.cfg.issuer:
                raise OidcError("issuer in discovery document does not match configuration")
            self._meta = meta
        return self._meta

    def authorization_url(self, state: str, nonce: str, verifier: str) -> str:
        params = {
            "response_type": "code",
            "client_id": self.cfg.client_id,
            "redirect_uri": self.cfg.redirect_uri,
            "scope": self.cfg.scopes,
            "state": state,
            "nonce": nonce,
            "code_challenge": challenge(verifier),
            "code_challenge_method": "S256",
        }
        return str(self.metadata()["authorization_endpoint"]) + "?" + urlencode(params)

    def _jwks(self) -> KeySet:
        if self._keys is None:
            data = self.http.get(self.metadata()["jwks_uri"]).raise_for_status().json()
            self._keys = KeySet.import_key_set(data)
        return self._keys

    def exchange(self, code: str, verifier: str, nonce: str) -> Identity:
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.cfg.redirect_uri,
            "client_id": self.cfg.client_id,
            "code_verifier": verifier,
        }
        if self.cfg.client_secret:
            data["client_secret"] = self.cfg.client_secret
        resp = self.http.post(self.metadata()["token_endpoint"], data=data)
        if resp.status_code != 200:
            raise OidcError("token endpoint refused the code")
        id_token = resp.json().get("id_token")
        if not id_token:
            raise OidcError("no id_token in the token response")
        return self.identity_from(id_token, nonce)

    def identity_from(self, id_token: str, nonce: str) -> Identity:
        try:
            try:
                token = jwt.decode(id_token, self._jwks(), algorithms=["RS256", "ES256"])
            except JoseError:
                # Keys rotate at the provider: fetch the set again once before refusing.
                self._keys = None
                token = jwt.decode(id_token, self._jwks(), algorithms=["RS256", "ES256"])
            registry = jwt.JWTClaimsRegistry(
                leeway=30,
                iss={"essential": True, "value": self.cfg.issuer},
                aud={"essential": True, "value": self.cfg.client_id},
                exp={"essential": True},
                nonce={"essential": True, "value": nonce},
            )
            registry.validate(token.claims)
        except JoseError as exc:
            raise OidcError(f"invalid id_token: {type(exc).__name__}") from None
        claims = token.claims
        if "sub" not in claims:
            raise OidcError("id_token has no subject")
        raw = claims.get(self.cfg.roles_claim, [])
        roles = frozenset(str(r) for r in raw) if isinstance(raw, list) else frozenset()
        name = str(claims.get("name") or claims.get("preferred_username") or claims["sub"])
        return Identity(subject=str(claims["sub"]), name=name, roles=roles)
