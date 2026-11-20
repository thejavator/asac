"""Port for policy evaluation (layer 3). The default adapter is OPA."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class Decision:
    block: list[str] = field(default_factory=list)
    escalate: bool = False


class PolicyEngine(Protocol):
    def evaluate(self, policy_path: str, package: str, input: dict[str, Any]) -> Decision: ...
