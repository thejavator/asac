"""Build a Tracker and a Wiki for a project from its variables.

Tracker: ``tracker_kind`` (jira|github|gitlab), ``tracker_url`` (Jira base URL, or the GitHub /
GitLab API URL), ``tracker_project`` (Jira: unused; GitHub/GitLab: ``owner/name``),
``tracker_user`` (Jira Cloud account email), ``tracker_token`` (vault reference).
Wiki: ``wiki_kind`` (confluence|gitlab), ``wiki_url``, ``wiki_space`` (Confluence space key) or
``wiki_project`` (GitLab ``group/name``), ``wiki_user``, ``wiki_token`` (vault reference).
URLs must be https. A project with no ``*_kind`` has no tracker or wiki: the factory answers
None and the portal shows plain text instead of links.
"""

from __future__ import annotations

from asac.adapters.tracker_http import GitHubIssues, GitLabIssues, Jira
from asac.adapters.vault import VaultError, resolve_vault
from asac.adapters.wiki_http import Confluence, GitLabWiki
from asac.ports.tracker import Tracker, TrackerError
from asac.ports.vars import VarsError, VarsStore
from asac.ports.wiki import Wiki, WikiError


def _vars(store: VarsStore) -> dict[str, str]:
    try:
        return {x.key: x.value for x in store.list()}
    except VarsError:
        return {}


def _https(url: str, key: str, error: type[Exception]) -> str:
    if not url.startswith("https://"):
        raise error(f"{key} must be an https URL")
    return url


def tracker_from_vars(store: VarsStore) -> Tracker | None:
    v = _vars(store)
    kind = v.get("tracker_kind")
    if not kind:
        return None
    try:
        token = resolve_vault(v.get("tracker_token", ""), "tracker_token")
    except VaultError as exc:
        raise TrackerError(str(exc)) from None
    url = v.get("tracker_url", "")
    project = v.get("tracker_project", "")
    if kind == "jira":
        return Jira(_https(url, "tracker_url", TrackerError), token, v.get("tracker_user") or None)
    if kind == "github":
        api = _https(url, "tracker_url", TrackerError) if url else "https://api.github.com"
        return GitHubIssues(project, token, api)
    if kind == "gitlab":
        api = _https(url, "tracker_url", TrackerError) if url else "https://gitlab.com/api/v4"
        return GitLabIssues(project, token, api)
    raise TrackerError(f"unknown tracker_kind '{kind}'")


def wiki_from_vars(store: VarsStore) -> Wiki | None:
    v = _vars(store)
    kind = v.get("wiki_kind")
    if not kind:
        return None
    try:
        token = resolve_vault(v.get("wiki_token", ""), "wiki_token")
    except VaultError as exc:
        raise WikiError(str(exc)) from None
    url = v.get("wiki_url", "")
    if kind == "confluence":
        return Confluence(
            _https(url, "wiki_url", WikiError),
            v.get("wiki_space", ""),
            token,
            v.get("wiki_user") or None,
        )
    if kind == "gitlab":
        api = _https(url, "wiki_url", WikiError) if url else "https://gitlab.com/api/v4"
        return GitLabWiki(v.get("wiki_project", ""), token, api)
    raise WikiError(f"unknown wiki_kind '{kind}'")
