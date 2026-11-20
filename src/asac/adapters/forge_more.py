"""Gitea/Forgejo, Bitbucket Cloud and Azure DevOps adapters for the Forge port.

Same rules as ``forge_http``: the token goes only in a header, never in an error message, and a
branch that moved is reported as ``Conflict`` (never overwritten, never forced).
"""

from __future__ import annotations

import base64
import re
from typing import Any
from urllib.parse import quote

import httpx

from asac.adapters.forge_http import _SHA, _check_branch, _check_path, _Http
from asac.ports.forge import (
    Author,
    Capabilities,
    ChangeRequest,
    Conflict,
    FileContent,
    ForgeError,
    NotFound,
)

_TRAILER = "\n\nAuthored-via: ASAC portal on behalf of {n} <{e}>"


def _trailer(author: Author) -> str:
    return _TRAILER.format(n=author.name, e=author.email)


def _check_sha(sha: str) -> None:
    if not _SHA.match(sha):
        raise ForgeError("from_sha must be a full commit id")


class GiteaForge:
    """Gitea and Forgejo (API v1; ``contents`` multi-file commits need Gitea 1.20+)."""

    def __init__(self, repo: str, token: str, api: str, client: httpx.Client | None = None) -> None:
        if not re.fullmatch(r"[\w.-]+/[\w.-]+", repo):
            raise ForgeError("repo must look like owner/name")
        self.repo = repo
        self.h = _Http(api, {"Authorization": f"token {token}"}, client)

    def _p(self, tail: str) -> str:
        return f"/repos/{self.repo}{tail}"

    def capabilities(self) -> Capabilities:
        return Capabilities(change_requests=True, members=True, webhooks=True)

    def default_branch(self) -> str:
        return str(self.h.call("GET", self._p(""))["default_branch"])

    def head(self, branch: str) -> str:
        b = self.h.call("GET", self._p(f"/branches/{quote(_check_branch(branch))}"))
        return str(b["commit"]["id"])

    def _file(self, path: str, ref: str) -> dict[str, Any]:
        got = self.h.call(
            "GET", self._p(f"/contents/{quote(_check_path(path))}"), params={"ref": ref}
        )
        if not isinstance(got, dict) or got.get("type") != "file":
            raise NotFound(f"no such file: {path}")
        return got

    def read_file(self, path: str, branch: str | None = None) -> FileContent:
        sha = self.head(branch or self.default_branch())
        got = self._file(path, sha)
        return FileContent(path, base64.b64decode(got["content"]).decode("utf-8"), sha)

    def create_branch(self, name: str, from_sha: str) -> None:
        _check_branch(name)
        _check_sha(from_sha)
        try:
            self.head(name)
        except NotFound:
            self.h.call(
                "POST", self._p("/branches"),
                json={"new_branch_name": name, "old_ref_name": from_sha},
            )  # fmt: skip
            return
        raise ForgeError(f"branch already exists: {name}")

    def commit_files(
        self, branch: str, files: dict[str, str], message: str, author: Author, base_sha: str
    ) -> str:
        current = self.head(branch)
        if current != base_sha:
            raise Conflict(f"{branch} moved since the draft was based on it", current)
        ops = []
        for p, c in files.items():
            op: dict[str, str] = {
                "path": _check_path(p),
                "content": base64.b64encode(c.encode()).decode(),
            }
            try:
                op["sha"] = str(self._file(p, current)["sha"])
                op["operation"] = "update"
            except NotFound:
                op["operation"] = "create"
            ops.append(op)
        try:
            done = self.h.call(
                "POST", self._p("/contents"),
                json={"branch": branch, "message": message + _trailer(author),
                      "author": {"name": author.name, "email": author.email},
                      "files": ops},
            )  # fmt: skip
        except ForgeError:
            now = self.head(branch)
            if now != current:
                raise Conflict(f"{branch} moved while committing", now) from None
            raise
        return str(done["commit"]["sha"])

    def _cr(self, d: dict[str, Any]) -> ChangeRequest:
        state = "merged" if d.get("merged") else str(d["state"])
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


class BitbucketForge:
    """Bitbucket Cloud (REST 2.0). ``repo`` is ``workspace/slug``; the token is a bearer token."""

    _RESERVED = {"message", "branch", "author", "parents"}

    def __init__(
        self,
        repo: str,
        token: str,
        api: str = "https://api.bitbucket.org/2.0",
        client: httpx.Client | None = None,
    ) -> None:
        if not re.fullmatch(r"[\w.-]+/[\w.-]+", repo):
            raise ForgeError("repo must look like workspace/slug")
        self.repo = repo
        self.h = _Http(api, {"Authorization": f"Bearer {token}"}, client)

    def _p(self, tail: str) -> str:
        return f"/repositories/{self.repo}{tail}"

    def capabilities(self) -> Capabilities:
        return Capabilities(change_requests=True, members=True, webhooks=True)

    def default_branch(self) -> str:
        return str(self.h.call("GET", self._p(""))["mainbranch"]["name"])

    def head(self, branch: str) -> str:
        b = self.h.call("GET", self._p(f"/refs/branches/{quote(_check_branch(branch))}"))
        return str(b["target"]["hash"])

    def read_file(self, path: str, branch: str | None = None) -> FileContent:
        sha = self.head(branch or self.default_branch())
        try:
            r = self.h.client.get(
                self.h.base + self._p(f"/src/{sha}/{quote(_check_path(path))}"),
                headers=self.h.headers,
            )
        except httpx.HTTPError as exc:
            raise ForgeError(f"forge unreachable: {type(exc).__name__}") from None
        if r.status_code == 404:
            raise NotFound(f"no such file: {path}")
        if r.status_code != 200:
            raise ForgeError(f"GET src answered {r.status_code}")
        return FileContent(path, r.content.decode("utf-8"), sha)  # bytes kept exactly

    def create_branch(self, name: str, from_sha: str) -> None:
        _check_branch(name)
        _check_sha(from_sha)
        try:
            self.head(name)
        except NotFound:
            self.h.call(
                "POST", self._p("/refs/branches"),
                json={"name": name, "target": {"hash": from_sha}},
            )  # fmt: skip
            return
        raise ForgeError(f"branch already exists: {name}")

    def commit_files(
        self, branch: str, files: dict[str, str], message: str, author: Author, base_sha: str
    ) -> str:
        current = self.head(branch)
        if current != base_sha:
            raise Conflict(f"{branch} moved since the draft was based on it", current)
        for p in files:
            if _check_path(p) in self._RESERVED:
                raise ForgeError(f"refused path: {p!r}")
        form = {
            **files,
            "message": message + _trailer(author),
            "branch": branch,
            "author": f"{author.name} <{author.email}>",
            "parents": current,
        }
        try:
            self.h.call("POST", self._p("/src"), ok=(200, 201), data=form)
        except ForgeError:
            now = self.head(branch)
            if now != current:
                raise Conflict(f"{branch} moved while committing", now) from None
            raise
        return self.head(branch)

    def _cr(self, d: dict[str, Any]) -> ChangeRequest:
        state = {"OPEN": "open", "MERGED": "merged"}.get(str(d["state"]), "closed")
        return ChangeRequest(
            str(d["id"]), d["links"]["html"]["href"], d["source"]["branch"]["name"],
            d["destination"]["branch"]["name"], state,
            d.get("author", {}).get("nickname", ""),
        )  # fmt: skip

    def open_change_request(
        self, source: str, target: str, title: str, description: str
    ) -> ChangeRequest:
        d = self.h.call(
            "POST", self._p("/pullrequests"),
            json={"title": title, "description": description,
                  "source": {"branch": {"name": source}},
                  "destination": {"branch": {"name": target}}},
        )  # fmt: skip
        return self._cr(d)

    def get_change_request(self, cr_id: str) -> ChangeRequest:
        if not cr_id.isdigit():
            raise NotFound("unknown change request")
        return self._cr(self.h.call("GET", self._p(f"/pullrequests/{cr_id}")))


class AzureDevOpsForge:
    """Azure DevOps Git. ``repo`` is ``organization/project/repository``; the token is a PAT."""

    _V = {"api-version": "7.1"}
    _ZERO = "0" * 40

    def __init__(
        self,
        repo: str,
        token: str,
        api: str = "https://dev.azure.com",
        client: httpx.Client | None = None,
    ) -> None:
        parts = repo.split("/")
        if len(parts) != 3 or not all(re.fullmatch(r"[\w. -]+", x) for x in parts):
            raise ForgeError("repo must look like organization/project/repository")
        org, project, name = (quote(x) for x in parts)
        self.web = f"{api.rstrip('/')}/{org}/{project}/_git/{name}"
        basic = base64.b64encode(f":{token}".encode()).decode()
        self.h = _Http(api, {"Authorization": f"Basic {basic}"}, client)
        self.root = f"/{org}/{project}/_apis/git/repositories/{name}"

    def _get(self, tail: str, **params: str) -> Any:
        return self.h.call("GET", self.root + tail, params={**self._V, **params})

    def capabilities(self) -> Capabilities:
        return Capabilities(change_requests=True, members=True, webhooks=True)

    def default_branch(self) -> str:
        return str(self._get("")["defaultBranch"]).removeprefix("refs/heads/")

    def head(self, branch: str) -> str:
        name = _check_branch(branch)
        got = self._get("/refs", filter=f"heads/{name}")
        for ref in got["value"]:
            if ref["name"] == f"refs/heads/{name}":
                return str(ref["objectId"])
        raise NotFound(f"no such branch: {name}")

    def _item(self, path: str, sha: str) -> str:
        got = self._get(
            "/items", path="/" + _check_path(path), includeContent="true", **{
                "versionDescriptor.version": sha, "versionDescriptor.versionType": "commit",
                "$format": "json",
            },
        )  # fmt: skip
        if not isinstance(got, dict) or "content" not in got:
            raise NotFound(f"no such file: {path}")
        return str(got["content"])

    def read_file(self, path: str, branch: str | None = None) -> FileContent:
        sha = self.head(branch or self.default_branch())
        return FileContent(path, self._item(path, sha), sha)

    def _push(self, body: dict[str, Any]) -> Any:
        return self.h.call("POST", self.root + "/pushes", params=self._V, json=body)

    def create_branch(self, name: str, from_sha: str) -> None:
        _check_branch(name)
        _check_sha(from_sha)
        try:
            self.head(name)
        except NotFound:
            got = self.h.call(
                "POST", self.root + "/refs", params=self._V,
                json=[{"name": f"refs/heads/{name}", "oldObjectId": self._ZERO,
                       "newObjectId": from_sha}],
            )  # fmt: skip
            if all(r.get("success") for r in got["value"]):
                return
            raise ForgeError(f"could not create branch {name}") from None
        raise ForgeError(f"branch already exists: {name}")

    def commit_files(
        self, branch: str, files: dict[str, str], message: str, author: Author, base_sha: str
    ) -> str:
        current = self.head(branch)
        if current != base_sha:
            raise Conflict(f"{branch} moved since the draft was based on it", current)
        changes = []
        for p, c in files.items():
            try:
                self._item(p, current)
                kind = "edit"
            except NotFound:
                kind = "add"
            changes.append({"changeType": kind, "item": {"path": "/" + _check_path(p)},
                            "newContent": {"content": c, "contentType": "rawtext"}})  # fmt: skip
        try:
            done = self._push({
                "refUpdates": [{"name": f"refs/heads/{branch}", "oldObjectId": current}],
                "commits": [{"comment": message + _trailer(author),
                             "author": {"name": author.name, "email": author.email},
                             "changes": changes}],
            })  # fmt: skip
        except ForgeError:
            now = self.head(branch)
            if now != current:
                raise Conflict(f"{branch} moved while committing", now) from None
            raise
        return str(done["commits"][0]["commitId"])

    def _cr(self, d: dict[str, Any]) -> ChangeRequest:
        state = {"active": "open", "completed": "merged"}.get(str(d["status"]), "closed")

        def strip(r: object) -> str:
            return str(r).removeprefix("refs/heads/")

        return ChangeRequest(
            str(d["pullRequestId"]), f"{self.web}/pullrequest/{d['pullRequestId']}",
            strip(d["sourceRefName"]), strip(d["targetRefName"]), state,
            d.get("createdBy", {}).get("uniqueName", ""),
        )  # fmt: skip

    def open_change_request(
        self, source: str, target: str, title: str, description: str
    ) -> ChangeRequest:
        d = self.h.call(
            "POST", self.root + "/pullrequests", params=self._V,
            json={"sourceRefName": f"refs/heads/{_check_branch(source)}",
                  "targetRefName": f"refs/heads/{_check_branch(target)}",
                  "title": title, "description": description},
        )  # fmt: skip
        return self._cr(d)

    def get_change_request(self, cr_id: str) -> ChangeRequest:
        if not cr_id.isdigit():
            raise NotFound("unknown change request")
        return self._cr(self._get(f"/pullrequests/{cr_id}"))
