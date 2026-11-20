"""In-memory fakes of the Jira, GitHub, GitLab and Confluence REST subsets (no sockets)."""

from __future__ import annotations

import httpx

SEEN: list[httpx.Request] = []


def _ok(body: object) -> httpx.Response:
    return httpx.Response(200, json=body)


def jira() -> httpx.MockTransport:
    def handle(req: httpx.Request) -> httpx.Response:
        SEEN.append(req)
        if req.url.path.endswith("/issue/PAY-139"):
            return _ok(
                {
                    "key": "PAY-139",
                    "fields": {
                        "summary": "Split refund and chargeback flows",
                        "status": {"name": "In Progress"},
                        "issuetype": {"name": "Story"},
                        "labels": ["asac-enabled"],
                    },
                }
            )
        return httpx.Response(404, json={})

    return httpx.MockTransport(handle)


def github_issues() -> httpx.MockTransport:
    def handle(req: httpx.Request) -> httpx.Response:
        SEEN.append(req)
        if req.url.path == "/repos/o/r/issues/12":
            return _ok(
                {"number": 12, "title": "Refunds", "state": "open", "labels": [{"name": "bug"}]}
            )
        return httpx.Response(404, json={})

    return httpx.MockTransport(handle)


def gitlab_issues() -> httpx.MockTransport:
    def handle(req: httpx.Request) -> httpx.Response:
        SEEN.append(req)
        if req.url.raw_path.decode() == "/api/v4/projects/g%2Fp/issues/12":
            return _ok({"iid": 12, "title": "Refunds", "state": "opened", "labels": ["bug"]})
        return httpx.Response(404, json={})

    return httpx.MockTransport(handle)


def confluence() -> httpx.MockTransport:
    page = {"id": "42", "title": "Refund policy", "_links": {"webui": "/spaces/PAY/pages/42"}}

    def handle(req: httpx.Request) -> httpx.Response:
        SEEN.append(req)
        if req.url.path == "/wiki/rest/api/content/search":
            text = req.url.params["cql"]
            return _ok({"results": [page] if "refund" in text.lower() else []})
        if req.url.path == "/wiki/rest/api/content/42":
            return _ok(page)
        return httpx.Response(404, json={})

    return httpx.MockTransport(handle)


def gitlab_wiki() -> httpx.MockTransport:
    pages = [{"slug": "refund-policy", "title": "Refund policy"}, {"slug": "home", "title": "Home"}]

    def handle(req: httpx.Request) -> httpx.Response:
        SEEN.append(req)
        path = req.url.raw_path.decode()
        if path == "/api/v4/projects/g%2Fp/wikis":
            return _ok(pages)
        if path == "/api/v4/projects/g%2Fp/wikis/refund-policy":
            return _ok(pages[0])
        return httpx.Response(404, json={})

    return httpx.MockTransport(handle)
