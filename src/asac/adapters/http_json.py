"""Small JSON-over-HTTP client shared by the tracker and wiki adapters.

Errors carry the method, the path without its query and the status code: never a header, a
query string or a body, so a credential cannot leak into a message or a log.
"""

from __future__ import annotations

import base64
from typing import Any

import httpx


def auth_headers(token: str, user: str | None) -> dict[str, str]:
    """Basic auth when a user is given (Atlassian Cloud: email + API token), else Bearer."""
    if user:
        raw = base64.b64encode(f"{user}:{token}".encode()).decode()
        return {"Authorization": f"Basic {raw}"}
    return {"Authorization": f"Bearer {token}"}


class JsonHttp:
    def __init__(
        self,
        base: str,
        headers: dict[str, str],
        client: httpx.Client | None,
        error: type[Exception],
        not_found: type[Exception],
        label: str,
    ) -> None:
        self.base = base.rstrip("/")
        self.headers = {"Accept": "application/json", **headers}
        self.client = client or httpx.Client(timeout=15, follow_redirects=False)
        self.error, self.not_found, self.label = error, not_found, label

    def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        where = path.split("?")[0]
        try:
            r = self.client.get(self.base + path, headers=self.headers, params=params)
        except httpx.HTTPError as exc:
            raise self.error(f"{self.label} unreachable: {type(exc).__name__}") from None
        if r.status_code == 404:
            raise self.not_found(f"{self.label}: {where} not found")
        if r.status_code != 200:
            raise self.error(f"{self.label}: GET {where} answered {r.status_code}")
        try:
            return r.json()
        except ValueError:
            raise self.error(f"{self.label}: GET {where} did not answer JSON") from None
