"""Conformance suites for the Tracker and Wiki ports, plus factory rules."""

from pathlib import Path

import httpx
import pytest

from asac.adapters.links_factory import tracker_from_vars, wiki_from_vars
from asac.adapters.tracker_http import GitHubIssues, GitLabIssues, Jira
from asac.adapters.vars_file import FileVarsStore
from asac.adapters.wiki_http import Confluence, GitLabWiki
from asac.ports.tracker import NotFound as IssueNotFound
from asac.ports.tracker import Tracker, TrackerError
from asac.ports.wiki import NotFound as PageNotFound
from asac.ports.wiki import Wiki, WikiError
from tests.conformance import fake_trackers as fk

SECRET = "tok-SECRET-123"
CLOUD = "https://acme.atlassian.net"


def _c(t: httpx.MockTransport) -> httpx.Client:
    return httpx.Client(transport=t)


TRACKERS = {
    "jira": (lambda: Jira("https://jira.test", SECRET, None, _c(fk.jira())), "PAY-139", "PAY-140"),
    "jira-cloud": (lambda: Jira(CLOUD, SECRET, "a@b.c", _c(fk.jira())), "PAY-139", "PAY-140"),
    "github": (lambda: GitHubIssues("o/r", SECRET, "https://api.test", client=_c(fk.github_issues())), "12", "13"),  # noqa: E501
    "gitlab": (lambda: GitLabIssues("g/p", SECRET, "https://gl.test/api/v4", _c(fk.gitlab_issues())), "12", "13"),  # noqa: E501
}  # fmt: skip


@pytest.mark.parametrize("kind", TRACKERS)
def test_tracker_contract(kind: str) -> None:
    make, good, missing = TRACKERS[kind]
    t: Tracker = make()
    assert t.valid_key(good) and not t.valid_key("../x") and not t.valid_key("")
    assert t.issue_url(good).endswith(good)
    issue = t.get_issue(good)
    assert issue.key == good and issue.title and issue.status and issue.url == t.issue_url(good)
    with pytest.raises(IssueNotFound):
        t.get_issue(missing)
    with pytest.raises(IssueNotFound):
        t.issue_url("a b")
    assert t.name and t.provider


def test_jira_details_and_auth_modes() -> None:
    fk.SEEN.clear()
    issue = Jira("https://jira.test", SECRET, None, _c(fk.jira())).get_issue("PAY-139")
    assert (issue.type, issue.labels, issue.url) == (
        "Story",
        ("asac-enabled",),
        "https://jira.test/browse/PAY-139",
    )
    assert fk.SEEN[-1].headers["authorization"] == f"Bearer {SECRET}"
    Jira(CLOUD, SECRET, "a@b.c", _c(fk.jira())).get_issue("PAY-139")
    assert fk.SEEN[-1].headers["authorization"].startswith("Basic ")
    assert fk.SEEN[-1].url.path.startswith("/rest/api/3/")


def test_tracker_errors_never_contain_the_token() -> None:
    def boom(_: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text=SECRET)

    def down(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(SECRET)

    for handler in (boom, down):
        j = Jira("https://jira.test", SECRET, None, _c(httpx.MockTransport(handler)))
        with pytest.raises(TrackerError) as ei:
            j.get_issue("PAY-1")
        assert SECRET not in str(ei.value)


WIKIS = {
    "confluence": lambda: Confluence(f"{CLOUD}/wiki", "PAY", SECRET, "a@b.c", _c(fk.confluence())),
    "gitlab": lambda: GitLabWiki("g/p", SECRET, "https://gl.test/api/v4", _c(fk.gitlab_wiki())),
}


@pytest.mark.parametrize("kind", WIKIS)
def test_wiki_contract(kind: str) -> None:
    w: Wiki = WIKIS[kind]()
    found = w.search("refund")
    assert [p.title for p in found] == ["Refund policy"] and found[0].url.startswith("https://")
    assert w.search("nothing-like-this") == []
    assert w.search("") == [] or kind == "gitlab"
    page = w.get_page(found[0].id)
    assert page.title == "Refund policy" and page.url == found[0].url
    with pytest.raises(PageNotFound):
        w.get_page("999" if kind == "confluence" else "nope")
    with pytest.raises(PageNotFound):
        w.get_page("../x")


def test_confluence_query_cannot_break_out_of_the_filter() -> None:
    fk.SEEN.clear()
    Confluence(f"{CLOUD}/wiki", "PAY", SECRET, None, _c(fk.confluence())).search('x" OR space = "Z')
    cql = fk.SEEN[-1].url.params["cql"]
    assert cql.count('"') == 4 and 'space = "PAY"' in cql
    with pytest.raises(WikiError):
        Confluence(CLOUD, 'PAY" OR', SECRET)


def vars_file(tmp_path: Path, **kv: str) -> FileVarsStore:
    store = FileVarsStore(tmp_path / "asac.vars.yaml")
    for k, v in kv.items():
        store.set(k, v)
    return store


def test_factories_need_kind_https_and_vault_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert tracker_from_vars(vars_file(tmp_path)) is None
    assert wiki_from_vars(vars_file(tmp_path)) is None
    monkeypatch.setenv("ASAC_VAULT_TEAM_JIRA", SECRET)
    ok = vars_file(
        tmp_path, tracker_kind="jira", tracker_url="https://j.test", tracker_token="${vault.team/jira}"  # noqa: E501
    )  # fmt: skip
    t = tracker_from_vars(ok)
    assert t is not None and t.provider == "jira"
    ok.set("tracker_url", "http://j.test")
    with pytest.raises(TrackerError, match="https"):
        tracker_from_vars(ok)
    ok.set("tracker_token", "${vault.team/absent}")
    with pytest.raises(TrackerError, match="not available") as ei:
        tracker_from_vars(ok)
    assert SECRET not in str(ei.value)
    bad = vars_file(tmp_path, wiki_kind="sharepoint", wiki_token="${vault.team/jira}")
    with pytest.raises(WikiError, match="unknown wiki_kind"):
        wiki_from_vars(bad)
    bad.set("wiki_kind", "confluence")
    bad.set("wiki_url", "https://c.test/wiki")
    bad.set("wiki_space", "PAY")
    w = wiki_from_vars(bad)
    assert w is not None and w.name == "Confluence"
