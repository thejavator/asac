"""Keys the manifest accepts that version 0.1 does not apply.

The manifest is validated against the whole spec (v0.4), but the engine applies a subset. A key
that is accepted and then ignored would let a person believe a rule is in force when it is not.
Each one is listed here, with the reason, and ``asac validate`` reports it (ASAC027).
It is a warning, never an error: the manifest is valid, and a later version may apply the key.
"""

from __future__ import annotations

from dataclasses import dataclass

from asac.model import Manifest

VERSION = "0.1"


@dataclass(frozen=True)
class Unapplied:
    key: str  # the top-level key, for the tests and the docs
    reason: str


UNAPPLIED = (
    Unapplied("knowledge", "knowledge sources are not given to the agent"),
    Unapplied("specLevel", "specLevel is checked by validate only; the engine does not enforce it"),
    Unapplied("provider.model", "the model chosen in a provider's config does not reach the tool"),
)


def unapplied_in(manifest: Manifest) -> list[tuple[str, str]]:
    """(path, message) for each accepted key that version 0.1 does not apply."""
    out: list[tuple[str, str]] = []
    reasons = {u.key: u.reason for u in UNAPPLIED}
    for name in manifest.knowledge:
        out.append((f"knowledge.{name}", _msg(reasons["knowledge"])))
    for aname, agent in manifest.agents.items():
        if agent.knowledge:
            out.append((f"agents.{aname}.knowledge", _msg(reasons["knowledge"])))
    for pname, pipe in manifest.pipelines.items():
        if pipe.specLevel:
            out.append((f"pipelines.{pname}.specLevel", _msg(reasons["specLevel"])))
    for prov, p in manifest.providers.items():
        if isinstance(p.config, dict) and "model" in p.config:
            out.append((f"providers.{prov}.config.model", _msg(reasons["provider.model"])))
    return out


def _msg(reason: str) -> str:
    return f"accepted but not applied in {VERSION}: {reason}"
