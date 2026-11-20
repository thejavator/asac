"""Deterministic harness for tests and dry runs. It never calls a model."""

from __future__ import annotations

import json
import os
from typing import Any

from asac.adapters.base import AdapterContext
from asac.ports.harness import HarnessDescriptor


class FakeHarness:
    descriptor = HarnessDescriptor(
        "fake", interactive=True, headless=True, mcp=True, streaming=True
    )

    def __init__(
        self, ctx: AdapterContext | None = None, fail_steps: frozenset[str] | None = None
    ) -> None:
        # ASAC_FAKE_FAIL=step1,step2 makes those steps raise, to test crash and resume.
        env = os.environ.get("ASAC_FAKE_FAIL", "")
        self._fail = (
            fail_steps if fail_steps is not None else frozenset(s for s in env.split(",") if s)
        )
        self.events: list[dict[str, Any]] = []
        self._mode = "assist"

    def mount(self, skill: str) -> None:
        self.events.append({"event": "mount", "skill": skill})

    def run(self, task: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        if task["step"] in self._fail:
            raise RuntimeError(f"fake harness failure at step {task['step']}")
        self.events.append({"event": "run", "step": task["step"]})
        # ASAC_FAKE_RESULT='{"tokens": 5}' merges extra fields into the report (governance tests).
        extra = json.loads(os.environ.get("ASAC_FAKE_RESULT", "{}"))
        if self._mode == "delegate" and os.environ.get("ASAC_FAKE_DELEGATE"):
            # Like a real harness in delegate mode: ask the engine to run a command in the runner.
            return {"status": "delegated", "tokens": 1000, "exec": ["claude", "-p", "work"]}
        return {"status": "ok", "tokens": 1000, **extra}

    def tools(self, mcp_servers: list[str]) -> None:
        self.events.append({"event": "tools", "servers": list(mcp_servers)})

    def permissions(self, mode: str) -> None:
        self._mode = mode
        self.events.append({"event": "permissions", "mode": mode})

    def emit(self, event: dict[str, Any]) -> None:
        self.events.append(dict(event))

    def describe(self) -> HarnessDescriptor:
        return self.descriptor

    def health_check(self) -> bool:
        return True
