"""Pipeline editor logic: validate a draft, propose it through the forge, detect conflicts.

Nothing here touches a checkout: content comes from the forge and goes back through it.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass, replace
from pathlib import Path

import yaml
from pydantic import ValidationError

from asac.loader.load import describe_validation_error
from asac.model import Manifest
from asac.ports.drafts import Draft, DraftStore
from asac.ports.forge import Author, Conflict, Forge
from asac.validate.checks import validate

MAX_BYTES = 256 * 1024


@dataclass(frozen=True)
class Finding:
    severity: str  # error | warning
    code: str
    path: str
    message: str


class DraftConflict(Exception):
    """The default branch changed the file since the draft was based on it."""

    def __init__(self, diff: str, current_sha: str) -> None:
        super().__init__("the default branch changed this file; rebase the draft")
        self.diff = diff
        self.current_sha = current_sha


def validate_text(content: str, root: Path) -> list[Finding]:
    """Syntax, schema, then the cross-reference rules of the full validator."""
    if len(content.encode()) > MAX_BYTES:
        return [Finding("error", "ASAC000", "", "file is larger than 256 KiB")]
    try:
        data = yaml.safe_load(content)
    except yaml.YAMLError as exc:
        return [Finding("error", "ASAC000", "", f"invalid YAML: {exc}".splitlines()[0])]
    if not isinstance(data, dict):
        return [Finding("error", "ASAC000", "", "expected a YAML mapping at the top level")]
    try:
        manifest = Manifest.model_validate(data)
    except ValidationError as exc:
        out = []
        for line in describe_validation_error(exc):
            head, _, msg = line.partition(": ")
            out.append(Finding("error", "ASAC000", head.split(" ", 2)[-1], msg))
        return out
    return [Finding(i.severity.value, i.code, i.path, i.message) for i in validate(manifest, root)]


def has_errors(findings: list[Finding]) -> bool:
    return any(f.severity == "error" for f in findings)


def unified_diff(old: str, new: str, path: str) -> str:
    return "".join(
        difflib.unified_diff(
            old.splitlines(keepends=True),
            new.splitlines(keepends=True),
            f"a/{path}",
            f"b/{path}",
        )
    )


def propose(
    draft: Draft,
    forge: Forge,
    store: DraftStore,
    root: Path,
    target: str,
    now: str,
) -> Draft:
    """Branch, commit and open a change request. Never pushes to the default branch."""
    if draft.status != "draft":
        raise ValueError(f"draft is already {draft.status}")
    if has_errors(validate_text(draft.content, root)):
        raise ValueError("the draft has validation errors")
    head = forge.head(target)
    if head != draft.base_sha:
        theirs = forge.read_file(draft.path, target)
        if theirs.content != draft.base_content:
            raise DraftConflict(unified_diff(draft.base_content, theirs.content, draft.path), head)
        draft = replace(draft, base_sha=head)  # file untouched upstream: safe to move the base
    if draft.content == draft.base_content:
        raise ValueError("nothing to propose: the draft equals the base file")
    branch = f"asac/pipeline-{draft.id}"
    forge.create_branch(branch, draft.base_sha)
    try:
        forge.commit_files(
            branch,
            {draft.path: draft.content},
            f"Change pipeline definition ({draft.id})",
            Author(draft.author_name, draft.author_email),
            draft.base_sha,
        )
    except Conflict as exc:
        raise DraftConflict("", exc.current_sha) from None
    cr = forge.open_change_request(
        branch,
        target,
        f"Pipeline change {draft.id} by {draft.author_name}",
        "Proposed from the ASAC portal. Review the diff; the author cannot approve their own "
        "change.\n\n" + unified_diff(draft.base_content, draft.content, draft.path),
    )
    done = replace(
        draft, status="proposed", branch=branch, cr_id=cr.id, cr_url=cr.url, updated_at=now
    )
    store.update(done)
    return done


def refresh(draft: Draft, forge: Forge, store: DraftStore, now: str) -> Draft:
    """Mark a proposed draft applied (merged) or closed, from the change request state."""
    if draft.status != "proposed" or draft.cr_id is None:
        return draft
    state = forge.get_change_request(draft.cr_id).state
    status = {"merged": "applied", "closed": "closed"}.get(state)
    if status is None:
        return draft
    done = replace(draft, status=status, updated_at=now)
    store.update(done)
    return done
