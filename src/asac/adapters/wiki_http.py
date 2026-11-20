"""Confluence and GitLab wiki adapters for the Wiki port (REST over httpx, read-only)."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote

import httpx

from asac.adapters.http_json import JsonHttp, auth_headers
from asac.ports.wiki import NotFound, Page, WikiError

_SPACE = re.compile(r"^[A-Za-z0-9~_-]{1,60}$")


class Confluence:
    """Confluence Cloud (``base_url`` ends in ``/wiki``, Basic auth) or Data Center (Bearer)."""

    name = "Confluence"

    def __init__(
        self,
        base_url: str,
        space: str,
        token: str,
        user: str | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        if not _SPACE.match(space):
            raise WikiError("wiki_space must be a Confluence space key")
        self.base_url, self.space = base_url.rstrip("/"), space
        self.h = JsonHttp(
            self.base_url, auth_headers(token, user), client, WikiError, NotFound, "Confluence"
        )

    def _page(self, d: dict[str, Any]) -> Page:
        link = str((d.get("_links") or {}).get("webui", ""))
        return Page(
            id=str(d.get("id", "")), title=str(d.get("title", "")), url=self.base_url + link
        )

    def search(self, query: str, limit: int = 10) -> list[Page]:
        text = query.replace("\\", " ").replace('"', " ").strip()
        if not text:
            return []
        cql = f'space = "{self.space}" AND type = page AND title ~ "{text}"'
        d: Any = self.h.get("/rest/api/content/search", {"cql": cql, "limit": max(1, limit)})
        return [self._page(x) for x in (d.get("results") or [])][:limit]

    def get_page(self, page_id: str) -> Page:
        if not page_id.isdigit():
            raise NotFound("unknown page")
        return self._page(self.h.get(f"/rest/api/content/{page_id}"))


class GitLabWiki:
    name = "GitLab wiki"

    def __init__(
        self,
        project: str,
        token: str,
        api: str = "https://gitlab.com/api/v4",
        client: httpx.Client | None = None,
    ) -> None:
        self.project = project
        self.pid = quote(project, safe="")
        self.web = re.sub(r"/api/v4/?$", "", api.rstrip("/"))
        self.h = JsonHttp(api, {"PRIVATE-TOKEN": token}, client, WikiError, NotFound, "GitLab")

    def _page(self, d: dict[str, Any]) -> Page:
        slug = str(d.get("slug", ""))
        return Page(
            id=slug,
            title=str(d.get("title", slug)),
            url=f"{self.web}/{self.project}/-/wikis/{quote(slug, safe='/')}",
        )

    def search(self, query: str, limit: int = 10) -> list[Page]:
        d: Any = self.h.get(f"/projects/{self.pid}/wikis")
        q = query.strip().lower()
        return [self._page(x) for x in d if q in str(x.get("title", "")).lower()][:limit]

    def get_page(self, page_id: str) -> Page:
        if not page_id or ".." in page_id.split("/"):
            raise NotFound("unknown page")
        return self._page(self.h.get(f"/projects/{self.pid}/wikis/{quote(page_id, safe='')}"))
