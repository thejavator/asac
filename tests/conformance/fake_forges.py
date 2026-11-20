"""In-memory fakes of the GitHub and GitLab REST subsets used by the adapters (no sockets)."""

from __future__ import annotations

import base64
import hashlib
import json
import re
from urllib.parse import unquote

import httpx


class Repo:
    def __init__(self) -> None:
        self.commits: dict[str, dict[str, str]] = {}
        self.branches: dict[str, str] = {}
        self.prs: list[dict[str, str]] = []
        self.n = 0
        self.token_seen: set[str] = set()
        self.commit("main", {"asac.yaml": "version: 1\n"})

    def commit(self, branch: str, changes: dict[str, str], parent: str | None = None) -> str:
        self.n += 1
        base = dict(self.commits.get(parent or self.branches.get(branch, ""), {}))
        base.update(changes)
        sha = hashlib.sha1(f"{self.n}{sorted(base.items())}".encode()).hexdigest()
        self.commits[sha] = base
        self.branches[branch] = sha
        return sha


def _json(code: int, body: object) -> httpx.Response:
    return httpx.Response(code, json=body)


def github(repo: Repo) -> httpx.MockTransport:
    def handle(req: httpx.Request) -> httpx.Response:
        repo.token_seen.add(req.headers.get("authorization", ""))
        path = unquote(req.url.path)
        body = json.loads(req.content) if req.content else {}
        if req.headers.get("authorization") != "Bearer tok":
            return _json(401, {})
        if path == "/repos/o/r":
            return _json(200, {"default_branch": "main"})
        if m := re.fullmatch(r"/repos/o/r/git/ref/heads/(.+)", path):
            sha = repo.branches.get(m[1])
            return _json(200, {"object": {"sha": sha}}) if sha else _json(404, {})
        if m := re.fullmatch(r"/repos/o/r/contents/(.+)", path):
            files = repo.commits.get(req.url.params["ref"], {})
            if m[1] not in files:
                return _json(404, {})
            enc = base64.b64encode(files[m[1]].encode()).decode()
            return _json(200, {"type": "file", "content": enc})
        if path == "/repos/o/r/git/refs" and req.method == "POST":
            repo.branches[body["ref"].removeprefix("refs/heads/")] = body["sha"]
            return _json(201, {})
        if m := re.fullmatch(r"/repos/o/r/git/commits/([0-9a-f]+)", path):
            return _json(200, {"tree": {"sha": m[1]}})
        if path == "/repos/o/r/git/trees":
            repo.n += 1
            tid = f"tree{repo.n}"
            repo.commits[tid] = {**repo.commits[body["base_tree"]],
                                 **{e["path"]: e["content"] for e in body["tree"]}}  # fmt: skip
            return _json(201, {"sha": tid})
        if path == "/repos/o/r/git/commits" and req.method == "POST":
            sha = hashlib.sha1(json.dumps(body, sort_keys=True).encode()).hexdigest()
            repo.commits[sha] = repo.commits[body["tree"]]
            repo.commits[f"msg-{sha}"] = {
                "message": body["message"],
                "author": body["author"]["name"],
            }
            return _json(201, {"sha": sha})
        if m := re.fullmatch(r"/repos/o/r/git/refs/heads/(.+)", path):
            return (
                _json(200, {})
                if repo.branches.update({m[1]: body["sha"]}) is None
                else _json(500, {})
            )
        if path == "/repos/o/r/pulls" and req.method == "POST":
            repo.prs.append({"head": body["head"], "base": body["base"]})
            n = len(repo.prs)
            return _json(201, _pr(n, repo.prs[-1]))
        if m := re.fullmatch(r"/repos/o/r/pulls/(\d+)", path):
            i = int(m[1])
            return _json(200, _pr(i, repo.prs[i - 1])) if i <= len(repo.prs) else _json(404, {})
        return _json(404, {})

    return httpx.MockTransport(handle)


def _pr(n: int, pr: dict[str, str]) -> dict[str, object]:
    return {
        "number": n,
        "html_url": f"https://x/pull/{n}",
        "state": "open",
        "merged_at": None,
        "head": {"ref": pr["head"]},
        "base": {"ref": pr["base"]},
        "user": {"login": "svc"},
    }


def gitlab(repo: Repo) -> httpx.MockTransport:
    def handle(req: httpx.Request) -> httpx.Response:
        if req.headers.get("private-token") != "tok":
            return _json(401, {})
        path = unquote(req.url.path).removeprefix("/api/v4")
        body = json.loads(req.content) if req.content else {}
        if path == "/projects/g/r":
            return _json(200, {"default_branch": "main"})
        if m := re.fullmatch(r"/projects/g/r/repository/branches/(.+)", path):
            sha = repo.branches.get(m[1])
            return _json(200, {"commit": {"id": sha}}) if sha else _json(404, {})
        if path == "/projects/g/r/repository/branches" and req.method == "POST":
            repo.branches[req.url.params["branch"]] = req.url.params["ref"]
            return _json(201, {})
        if m := re.fullmatch(r"/projects/g/r/repository/files/(.+)", path):
            files = repo.commits.get(req.url.params["ref"], {})
            if m[1] not in files:
                return _json(404, {})
            return _json(200, {"content": base64.b64encode(files[m[1]].encode()).decode()})
        if path == "/projects/g/r/repository/commits":
            if repo.branches.get(body["branch"]) != body["start_sha"]:
                return _json(400, {})
            sha = repo.commit(
                body["branch"], {a["file_path"]: a["content"] for a in body["actions"]}
            )
            repo.commits[f"msg-{sha}"] = {
                "message": body["commit_message"],
                "author": body["author_name"],
            }
            return _json(201, {"id": sha})
        if path == "/projects/g/r/merge_requests" and req.method == "POST":
            repo.prs.append({"head": body["source_branch"], "base": body["target_branch"]})
            return _json(201, _mr(len(repo.prs), repo.prs[-1]))
        if m := re.fullmatch(r"/projects/g/r/merge_requests/(\d+)", path):
            i = int(m[1])
            return _json(200, _mr(i, repo.prs[i - 1])) if i <= len(repo.prs) else _json(404, {})
        return _json(404, {})

    return httpx.MockTransport(handle)


def _mr(n: int, pr: dict[str, str]) -> dict[str, object]:
    return {"iid": n, "web_url": f"https://x/mr/{n}", "state": "opened",
            "source_branch": pr["head"], "target_branch": pr["base"],
            "author": {"username": "svc"}}  # fmt: skip


def gitea(repo: Repo) -> httpx.MockTransport:
    def handle(req: httpx.Request) -> httpx.Response:
        if req.headers.get("authorization") != "token tok":
            return _json(401, {})
        path = unquote(req.url.path).removeprefix("/api/v1")
        body = json.loads(req.content) if req.content else {}
        if path == "/repos/o/r":
            return _json(200, {"default_branch": "main"})
        if m := re.fullmatch(r"/repos/o/r/branches/(.+)", path):
            sha = repo.branches.get(m[1])
            return _json(200, {"commit": {"id": sha}}) if sha else _json(404, {})
        if path == "/repos/o/r/branches" and req.method == "POST":
            repo.branches[body["new_branch_name"]] = body["old_ref_name"]
            return _json(201, {})
        if m := re.fullmatch(r"/repos/o/r/contents/(.+)", path):
            files = repo.commits.get(req.url.params["ref"], {})
            if m[1] not in files:
                return _json(404, {})
            enc = base64.b64encode(files[m[1]].encode()).decode()
            return _json(200, {"type": "file", "content": enc, "sha": "blob"})
        if path == "/repos/o/r/contents" and req.method == "POST":
            sha = repo.commit(
                body["branch"],
                {f["path"]: base64.b64decode(f["content"]).decode() for f in body["files"]},
            )
            repo.commits[f"msg-{sha}"] = {
                "message": body["message"],
                "author": body["author"]["name"],
            }
            return _json(201, {"commit": {"sha": sha}})
        if path == "/repos/o/r/pulls" and req.method == "POST":
            repo.prs.append({"head": body["head"], "base": body["base"]})
            return _json(201, _pr(len(repo.prs), repo.prs[-1]) | {"merged": False})
        if m := re.fullmatch(r"/repos/o/r/pulls/(\d+)", path):
            i = int(m[1])
            if i > len(repo.prs):
                return _json(404, {})
            return _json(200, _pr(i, repo.prs[i - 1]) | {"merged": False})
        return _json(404, {})

    return httpx.MockTransport(handle)


def bitbucket(repo: Repo) -> httpx.MockTransport:
    def handle(req: httpx.Request) -> httpx.Response:
        if req.headers.get("authorization") != "Bearer tok":
            return _json(401, {})
        path = unquote(req.url.path).removeprefix("/2.0")
        if path == "/repositories/w/r":
            return _json(200, {"mainbranch": {"name": "main"}})
        if m := re.fullmatch(r"/repositories/w/r/refs/branches/(.+)", path):
            sha = repo.branches.get(m[1])
            return _json(200, {"target": {"hash": sha}}) if sha else _json(404, {})
        if path == "/repositories/w/r/refs/branches" and req.method == "POST":
            body = json.loads(req.content)
            repo.branches[body["name"]] = body["target"]["hash"]
            return _json(201, {})
        if m := re.fullmatch(r"/repositories/w/r/src/([0-9a-f]{40})/(.+)", path):
            files = repo.commits.get(m[1], {})
            if m[2] not in files:
                return _json(404, {})
            return httpx.Response(200, content=files[m[2]].encode())
        if path == "/repositories/w/r/src" and req.method == "POST":
            form = dict(x.split("=", 1) for x in req.content.decode().split("&"))
            f = {
                unquote(k).replace("+", " "): unquote(v).replace("+", " ") for k, v in form.items()
            }
            branch = f.pop("branch")
            if repo.branches.get(branch) != f.pop("parents"):
                return _json(400, {})
            msg, who = f.pop("message"), f.pop("author")
            sha = repo.commit(branch, f)
            repo.commits[f"msg-{sha}"] = {"message": msg, "author": who}
            return httpx.Response(201)
        if path == "/repositories/w/r/pullrequests" and req.method == "POST":
            body = json.loads(req.content)
            repo.prs.append({"head": body["source"]["branch"]["name"],
                             "base": body["destination"]["branch"]["name"]})  # fmt: skip
            return _json(201, _bb_pr(len(repo.prs), repo.prs[-1]))
        if m := re.fullmatch(r"/repositories/w/r/pullrequests/(\d+)", path):
            i = int(m[1])
            return _json(200, _bb_pr(i, repo.prs[i - 1])) if i <= len(repo.prs) else _json(404, {})
        return _json(404, {})

    return httpx.MockTransport(handle)


def _bb_pr(n: int, pr: dict[str, str]) -> dict[str, object]:
    return {"id": n, "state": "OPEN", "links": {"html": {"href": f"https://x/pr/{n}"}},
            "source": {"branch": {"name": pr["head"]}},
            "destination": {"branch": {"name": pr["base"]}},
            "author": {"nickname": "svc"}}  # fmt: skip


def azure(repo: Repo) -> httpx.MockTransport:
    root = "/org/proj/_apis/git/repositories/r"

    def handle(req: httpx.Request) -> httpx.Response:
        want = "Basic " + base64.b64encode(b":tok").decode()
        if req.headers.get("authorization") != want:
            return _json(401, {})
        path = unquote(req.url.path)
        q = req.url.params
        body = json.loads(req.content) if req.content else {}
        if path == root:
            return _json(200, {"defaultBranch": "refs/heads/main"})
        if path == root + "/refs" and req.method == "GET":
            name = q["filter"].removeprefix("heads/")
            sha = repo.branches.get(name)
            vals = [{"name": f"refs/heads/{name}", "objectId": sha}] if sha else []
            return _json(200, {"value": vals})
        if path == root + "/refs" and req.method == "POST":
            for u in body:
                repo.branches[u["name"].removeprefix("refs/heads/")] = u["newObjectId"]
            return _json(200, {"value": [{"success": True} for _ in body]})
        if path == root + "/items":
            files = repo.commits.get(q["versionDescriptor.version"], {})
            p = q["path"].removeprefix("/")
            if p not in files:
                return _json(404, {})
            return _json(200, {"path": q["path"], "content": files[p]})
        if path == root + "/pushes":
            upd, commit = body["refUpdates"][0], body["commits"][0]
            branch = upd["name"].removeprefix("refs/heads/")
            if repo.branches.get(branch) != upd["oldObjectId"]:
                return _json(409, {})
            sha = repo.commit(
                branch, {c["item"]["path"].removeprefix("/"): c["newContent"]["content"]
                         for c in commit["changes"]},
            )  # fmt: skip
            repo.commits[f"msg-{sha}"] = {
                "message": commit["comment"],
                "author": commit["author"]["name"],
            }
            return _json(201, {"commits": [{"commitId": sha}]})
        if path == root + "/pullrequests" and req.method == "POST":
            repo.prs.append({"head": body["sourceRefName"].removeprefix("refs/heads/"),
                             "base": body["targetRefName"].removeprefix("refs/heads/")})  # fmt: skip  # noqa: E501
            return _json(201, _az_pr(len(repo.prs), repo.prs[-1]))
        if m := re.fullmatch(root + r"/pullrequests/(\d+)", path):
            i = int(m[1])
            return _json(200, _az_pr(i, repo.prs[i - 1])) if i <= len(repo.prs) else _json(404, {})
        return _json(404, {})

    return httpx.MockTransport(handle)


def _az_pr(n: int, pr: dict[str, str]) -> dict[str, object]:
    return {"pullRequestId": n, "status": "active",
            "sourceRefName": f"refs/heads/{pr['head']}",
            "targetRefName": f"refs/heads/{pr['base']}",
            "createdBy": {"uniqueName": "svc"}}  # fmt: skip
