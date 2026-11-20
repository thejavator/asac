"""Jira, GitHub issues and GitLab issues adapters for the Tracker port (REST over httpx).

Tokens are constructor arguments resolved from the vault by the factory; they go only in a
request header. ``issue_url`` needs no network call.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote

import httpx

from asac.adapters.http_json import JsonHttp, auth_headers
from asac.ports.tracker import Issue, NotFound, TrackerError


class Jira:
    """Jira Cloud (``user`` = account email, Basic auth) or Data Center (Bearer PAT)."""

    name = "Jira"
    provider = "jira"
    _KEY = re.compile(r"^[A-Z][A-Z0-9_]{1,9}-\d{1,9}$")

    def __init__(
        self,
        base_url: str,
        token: str,
        user: str | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.h = JsonHttp(
            self.base_url, auth_headers(token, user), client, TrackerError, NotFound, "Jira"
        )
        self.api = "/rest/api/2" if not user else "/rest/api/3"

    def valid_key(self, key: str) -> bool:
        return bool(self._KEY.match(key))

    def issue_url(self, key: str) -> str:
        if not self.valid_key(key):
            raise NotFound(f"not a Jira issue key: {key!r}")
        return f"{self.base_url}/browse/{key}"

    def get_issue(self, key: str) -> Issue:
        url = self.issue_url(key)
        data: Any = self.h.get(
            f"{self.api}/issue/{key}", {"fields": "summary,status,issuetype,labels"}
        )
        f = data.get("fields") or {}
        return Issue(
            key=str(data.get("key", key)),
            title=str(f.get("summary", "")),
            status=str((f.get("status") or {}).get("name", "")),
            url=url,
            type=str((f.get("issuetype") or {}).get("name", "")),
            labels=tuple(str(x) for x in f.get("labels") or []),
        )


class GitHubIssues:
    name = "GitHub"
    provider = "github"

    def __init__(
        self,
        repo: str,
        token: str,
        api: str = "https://api.github.com",
        web: str = "https://github.com",
        client: httpx.Client | None = None,
    ) -> None:
        if not re.fullmatch(r"[\w.-]+/[\w.-]+", repo):
            raise TrackerError("repo must look like owner/name")
        self.repo, self.web = repo, web.rstrip("/")
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        self.h = JsonHttp(api, headers, client, TrackerError, NotFound, "GitHub")

    def valid_key(self, key: str) -> bool:
        return key.isdigit() and len(key) <= 9

    def issue_url(self, key: str) -> str:
        if not self.valid_key(key):
            raise NotFound(f"not an issue number: {key!r}")
        return f"{self.web}/{self.repo}/issues/{key}"

    def get_issue(self, key: str) -> Issue:
        url = self.issue_url(key)
        d: Any = self.h.get(f"/repos/{self.repo}/issues/{key}")
        return Issue(
            key=str(d.get("number", key)),
            title=str(d.get("title", "")),
            status=str(d.get("state", "")),
            url=url,
            type="pull request" if d.get("pull_request") else "issue",
            labels=tuple(str(x.get("name", "")) for x in d.get("labels") or []),
        )


class GitLabIssues:
    name = "GitLab"
    provider = "gitlab"

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
        self.h = JsonHttp(api, {"PRIVATE-TOKEN": token}, client, TrackerError, NotFound, "GitLab")

    def valid_key(self, key: str) -> bool:
        return key.isdigit() and len(key) <= 9

    def issue_url(self, key: str) -> str:
        if not self.valid_key(key):
            raise NotFound(f"not an issue number: {key!r}")
        return f"{self.web}/{self.project}/-/issues/{key}"

    def get_issue(self, key: str) -> Issue:
        url = self.issue_url(key)
        d: Any = self.h.get(f"/projects/{self.pid}/issues/{key}")
        return Issue(
            key=str(d.get("iid", key)),
            title=str(d.get("title", "")),
            status=str(d.get("state", "")),
            url=url,
            type=str(d.get("issue_type", "issue")),
            labels=tuple(str(x) for x in d.get("labels") or []),
        )
