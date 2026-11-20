"""GitHub and GitLab adapters for the Forge port (REST over httpx, no new dependency).

The token is a constructor argument resolved from the vault by the caller. It goes only in a
request header and never appears in an error message. Writes never force: a moved branch is
reported as ``Conflict``.
"""

from __future__ import annotations

import base64
import re
from typing import Any
from urllib.parse import quote

import httpx

from asac.ports.forge import (
    Author,
    Capabilities,
    ChangeRequest,
    Conflict,
    FileContent,
    ForgeError,
    NotFound,
)

_SHA = re.compile(r"^[0-9a-f]{40}$")
_BRANCH = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,100}$")


def _check_path(path: str) -> str:
    parts = path.split("/")
    if not path or path.startswith("/") or ".." in parts or "\x00" in path or "" in parts:
        raise ForgeError(f"refused path: {path!r}")
    return path


def _check_branch(name: str) -> str:
    if not _BRANCH.match(name) or ".." in name or name.endswith(("/", ".lock")):
        raise ForgeError(f"refused branch name: {name!r}")
    return name


class _Http:
    def __init__(self, base: str, headers: dict[str, str], client: httpx.Client | None) -> None:
        self.base = base.rstrip("/")
        self.client = client or httpx.Client(timeout=20, follow_redirects=False)
        self.headers = headers

    def call(self, method: str, path: str, *, ok: tuple[int, ...] = (200, 201), **kw: Any) -> Any:
        try:
            r = self.client.request(method, self.base + path, headers=self.headers, **kw)
        except httpx.HTTPError as exc:
            raise ForgeError(f"forge unreachable: {type(exc).__name__}") from None
        if r.status_code == 404:
            raise NotFound(f"{method} {path.split('?')[0]}: not found")
        if r.status_code not in ok:
            raise ForgeError(f"{method} {path.split('?')[0]} answered {r.status_code}")
        return r.json() if r.content else None


class GitHubForge:
    def __init__(
        self,
        repo: str,
        token: str,
        api: str = "https://api.github.com",
        client: httpx.Client | None = None,
    ) -> None:
        if not re.fullmatch(r"[\w.-]+/[\w.-]+", repo):
            raise ForgeError("repo must look like owner/name")
        self.repo = repo
        self.h = _Http(
            api,
            {
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            client,
        )

    def _p(self, tail: str) -> str:
        return f"/repos/{self.repo}{tail}"

    def capabilities(self) -> Capabilities:
        return Capabilities(change_requests=True, members=True, webhooks=True)

    def default_branch(self) -> str:
        return str(self.h.call("GET", self._p(""))["default_branch"])

    def head(self, branch: str) -> str:
        ref = self.h.call("GET", self._p(f"/git/ref/heads/{quote(_check_branch(branch))}"))
        return str(ref["object"]["sha"])

    def read_file(self, path: str, branch: str | None = None) -> FileContent:
        branch = _check_branch(branch or self.default_branch())
        sha = self.head(branch)
        got = self.h.call(
            "GET", self._p(f"/contents/{quote(_check_path(path))}"), params={"ref": sha}
        )
        if not isinstance(got, dict) or got.get("type") != "file":
            raise NotFound(f"no such file: {path}")
        return FileContent(path, base64.b64decode(got["content"]).decode("utf-8"), sha)

    def create_branch(self, name: str, from_sha: str) -> None:
        _check_branch(name)
        if not _SHA.match(from_sha):
            raise ForgeError("from_sha must be a full commit id")
        try:
            self.head(name)
        except NotFound:
            self.h.call(
                "POST", self._p("/git/refs"), json={"ref": f"refs/heads/{name}", "sha": from_sha}
            )
            return
        raise ForgeError(f"branch already exists: {name}")

    def commit_files(
        self, branch: str, files: dict[str, str], message: str, author: Author, base_sha: str
    ) -> str:
        current = self.head(branch)
        if current != base_sha:
            raise Conflict(f"{branch} moved since the draft was based on it", current)
        base_commit = self.h.call("GET", self._p(f"/git/commits/{current}"))
        tree = self.h.call(
            "POST",
            self._p("/git/trees"),
            json={
                "base_tree": base_commit["tree"]["sha"],
                "tree": [
                    {"path": _check_path(p), "mode": "100644", "type": "blob", "content": c}
                    for p, c in files.items()
                ],
            },
        )
        commit = self.h.call(
            "POST",
            self._p("/git/commits"),
            json={
                "message": f"{message}\n\nAuthored-via: ASAC portal on behalf of "
                f"{author.name} <{author.email}>",
                "tree": tree["sha"],
                "parents": [current],
                "author": {"name": author.name, "email": author.email},
            },
        )
        try:  # force=false: GitHub refuses a non fast-forward update
            self.h.call(
                "PATCH",
                self._p(f"/git/refs/heads/{quote(branch)}"),
                json={"sha": commit["sha"], "force": False},
            )
        except ForgeError:
            raise Conflict(f"{branch} moved while committing", self.head(branch)) from None
        return str(commit["sha"])

    def _cr(self, d: dict[str, Any]) -> ChangeRequest:
        state = "merged" if d.get("merged_at") else str(d["state"])
        return ChangeRequest(
            str(d["number"]), d["html_url"], d["head"]["ref"], d["base"]["ref"], state,
            d["user"]["login"],
        )  # fmt: skip

    def open_change_request(
        self, source: str, target: str, title: str, description: str
    ) -> ChangeRequest:
        d = self.h.call(
            "POST", self._p("/pulls"),
            json={"head": source, "base": target, "title": title, "body": description},
        )  # fmt: skip
        return self._cr(d)

    def get_change_request(self, cr_id: str) -> ChangeRequest:
        if not cr_id.isdigit():
            raise NotFound("unknown change request")
        return self._cr(self.h.call("GET", self._p(f"/pulls/{cr_id}")))


class GitLabForge:
    def __init__(
        self,
        project: str,
        token: str,
        api: str = "https://gitlab.com/api/v4",
        client: httpx.Client | None = None,
    ) -> None:
        self.pid = quote(project, safe="")  # "group/sub/name" or a numeric id
        self.h = _Http(api, {"PRIVATE-TOKEN": token}, client)

    def _p(self, tail: str) -> str:
        return f"/projects/{self.pid}{tail}"

    def capabilities(self) -> Capabilities:
        return Capabilities(change_requests=True, members=True, webhooks=True)

    def default_branch(self) -> str:
        return str(self.h.call("GET", self._p(""))["default_branch"])

    def head(self, branch: str) -> str:
        b = self.h.call(
            "GET", self._p(f"/repository/branches/{quote(_check_branch(branch), safe='')}")
        )
        return str(b["commit"]["id"])

    def read_file(self, path: str, branch: str | None = None) -> FileContent:
        branch = _check_branch(branch or self.default_branch())
        sha = self.head(branch)
        got = self.h.call(
            "GET", self._p(f"/repository/files/{quote(_check_path(path), safe='')}"),
            params={"ref": sha},
        )  # fmt: skip
        return FileContent(path, base64.b64decode(got["content"]).decode("utf-8"), sha)

    def create_branch(self, name: str, from_sha: str) -> None:
        _check_branch(name)
        if not _SHA.match(from_sha):
            raise ForgeError("from_sha must be a full commit id")
        try:
            self.head(name)
        except NotFound:
            self.h.call(
                "POST", self._p("/repository/branches"), params={"branch": name, "ref": from_sha}
            )
            return
        raise ForgeError(f"branch already exists: {name}")

    def commit_files(
        self, branch: str, files: dict[str, str], message: str, author: Author, base_sha: str
    ) -> str:
        current = self.head(branch)
        if current != base_sha:
            raise Conflict(f"{branch} moved since the draft was based on it", current)
        actions = []
        for p, c in files.items():
            _check_path(p)
            try:
                self.h.call(
                    "GET",
                    self._p(f"/repository/files/{quote(p, safe='')}"),
                    params={"ref": current},
                )
                kind = "update"
            except NotFound:
                kind = "create"
            actions.append({"action": kind, "file_path": p, "content": c})
        done = self.h.call(
            "POST",
            self._p("/repository/commits"),
            json={
                "branch": branch,
                "start_sha": current,  # GitLab refuses if the branch is not at this commit
                "commit_message": f"{message}\n\nAuthored-via: ASAC portal on behalf of "
                f"{author.name} <{author.email}>",
                "author_name": author.name,
                "author_email": author.email,
                "actions": actions,
            },
        )
        return str(done["id"])

    def _cr(self, d: dict[str, Any]) -> ChangeRequest:
        state = {"opened": "open"}.get(d["state"], d["state"])
        return ChangeRequest(
            str(d["iid"]), d["web_url"], d["source_branch"], d["target_branch"], state,
            d["author"]["username"],
        )  # fmt: skip

    def open_change_request(
        self, source: str, target: str, title: str, description: str
    ) -> ChangeRequest:
        d = self.h.call(
            "POST", self._p("/merge_requests"),
            json={"source_branch": source, "target_branch": target, "title": title,
                  "description": description},
        )  # fmt: skip
        return self._cr(d)

    def get_change_request(self, cr_id: str) -> ChangeRequest:
        if not cr_id.isdigit():
            raise NotFound("unknown change request")
        return self._cr(self.h.call("GET", self._p(f"/merge_requests/{cr_id}")))
