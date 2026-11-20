"""Event envelope and trigger matching.

Jira ``issue_created``, GitHub ``issues``/``opened`` and GitLab issue ``open`` events are
mapped to one provider-neutral ``Event``. GitHub and GitLab issue openings are both named
``issue_opened``; the trigger filter reads ``labels`` (and ``issuetype`` for Jira).
"""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from typing import Any

from asac.model import Manifest
from asac.model.manifest import Trigger


@dataclass(frozen=True)
class Event:
    """Provider-neutral envelope. Any event bus can post this shape."""

    provider: str
    event: str
    key: str  # stable id of the thing that happened, e.g. the Jira issue key
    attributes: dict[str, Any]


def parse_jira(payload: dict[str, Any]) -> Event | None:
    """Map a Jira webhook body to an Event. Returns None when it is not an issue event."""
    event = str(payload.get("webhookEvent", ""))
    issue = payload.get("issue")
    if not isinstance(issue, dict) or not event.startswith("jira:issue_"):
        return None
    fields = issue.get("fields") or {}
    issuetype = (fields.get("issuetype") or {}).get("name", "")
    labels = [str(x) for x in fields.get("labels") or []]
    return Event(
        provider="jira",
        event=event.removeprefix("jira:"),
        key=str(issue.get("key", "")),
        attributes={"issuetype": issuetype, "labels": labels},
    )


def parse_github(event_header: str | None, payload: dict[str, Any]) -> Event | None:
    """``X-GitHub-Event: issues`` with ``action: opened`` (or ``labeled``). Pull requests are
    not issues here."""
    issue = payload.get("issue")
    if event_header != "issues" or not isinstance(issue, dict):
        return None
    action = str(payload.get("action", ""))
    if action not in ("opened", "labeled"):
        return None
    labels = [str(x.get("name", "")) for x in issue.get("labels") or [] if isinstance(x, dict)]
    return Event(
        provider="github",
        event="issue_opened" if action == "opened" else "issue_labeled",
        key=str(issue.get("number", "")),
        attributes={"labels": labels, "issuetype": "issue"},
    )


def parse_gitlab(payload: dict[str, Any]) -> Event | None:
    """``object_kind: issue`` with ``object_attributes.action`` ``open`` or ``update``."""
    attrs = payload.get("object_attributes")
    if payload.get("object_kind") != "issue" or not isinstance(attrs, dict):
        return None
    action = str(attrs.get("action", ""))
    if action not in ("open", "update"):
        return None
    labels = [str(x.get("title", "")) for x in payload.get("labels") or [] if isinstance(x, dict)]
    return Event(
        provider="gitlab",
        event="issue_opened" if action == "open" else "issue_updated",
        key=str(attrs.get("iid", "")),
        attributes={"labels": labels, "issuetype": str(attrs.get("issue_type", "issue"))},
    )


def safe_key(key: str) -> bool:
    """Keys end up in run ids: letters, digits and dashes only."""
    return 0 < len(key) <= 40 and all(c.isalnum() or c == "-" for c in key)


def matches(trigger: Trigger, ev: Event) -> bool:
    if trigger.type != "event":
        return False
    if trigger.provider and trigger.provider != ev.provider:
        return False
    if trigger.event and trigger.event != ev.event:
        return False
    for key, want in trigger.filter.items():
        have = ev.attributes.get(key)
        if isinstance(want, list):
            # every wanted value must be present (labels: [asac-enabled])
            have_list = have if isinstance(have, list) else [have]
            if not all(w in have_list for w in want):
                return False
        elif have != want:
            return False
    return True


def pipelines_for(manifest: Manifest, ev: Event) -> list[str]:
    return [name for name, p in manifest.pipelines.items() if p.trigger and matches(p.trigger, ev)]


def sign(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def verify_signature(secret: str, body: bytes, header: str | None) -> bool:
    """Constant-time check of an ``X-Hub-Signature``-style header."""
    return bool(header) and hmac.compare_digest(sign(secret, body), header or "")
