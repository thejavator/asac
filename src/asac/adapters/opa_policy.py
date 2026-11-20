"""OPA adapter for the ``PolicyEngine`` port: shells out to the ``opa`` binary (offline)."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from asac.ports.policy import Decision


class OpaUnavailable(Exception):
    pass


class OpaPolicyEngine:
    def __init__(self, root: Path, opa: str | None = None) -> None:
        self._root = root.resolve()
        self._opa = opa or shutil.which("opa") or ""

    def evaluate(self, policy_path: str, package: str, input: dict[str, Any]) -> Decision:
        if not self._opa:
            raise OpaUnavailable("the 'opa' binary is not on PATH (brew install opa)")
        policy = (self._root / policy_path).resolve()
        if not policy.is_relative_to(self._root) or not policy.is_file():
            raise OpaUnavailable(f"policy '{policy_path}' not found in the repository")
        query = f"data.{package}"
        proc = subprocess.run(
            [self._opa, "eval", "--format", "json", "--stdin-input", "-d", str(policy), query],
            input=json.dumps(input),
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if proc.returncode != 0:
            raise OpaUnavailable(f"opa failed: {proc.stderr.strip()}")
        return parse_decision(json.loads(proc.stdout), package)


def parse_decision(result: dict[str, Any], package: str) -> Decision:
    """Turn ``opa eval`` JSON into a Decision. ``block`` is a set of reasons."""
    exprs = result.get("result") or []
    value: dict[str, Any] = exprs[0]["expressions"][0]["value"] if exprs else {}
    block = value.get("block", []) or []
    if isinstance(block, dict):
        block = list(block)
    return Decision(block=sorted(str(b) for b in block), escalate=bool(value.get("escalate")))


__all__ = ["OpaPolicyEngine", "OpaUnavailable", "parse_decision"]
