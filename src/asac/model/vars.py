"""Layer 2 model: ``asac.vars.yaml``. Values only, never structure."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

# Keys that configure the platform itself. They are not ``var.*`` values,
# so ``asac vars diff`` must never report them as unused.
RESERVED_VARS_KEYS: frozenset[str] = frozenset(
    {
        "state_backend",
        "data_residency",
        # What ASAC itself reads from this file (see engine/runtime.py and adapters/):
        "autorun",
        "autorun_timeout",
        "isolate",
        "notify_targets",
        "parallel",
        "retries",
        "sandbox",
        "sandbox_domains",
        "runner_kind",
        "runner_image",
        "runner_network",
        "runner_env",
        "runner_k8s_context",
        "runner_k8s_namespace",
        "runner_k8s_pvc",
        "runner_k8s_secret",
    }
)


class VarsFile(BaseModel):
    model_config = ConfigDict(extra="allow")

    @property
    def values(self) -> dict[str, Any]:
        return dict(self.model_extra or {})

    def user_values(self) -> dict[str, Any]:
        return {k: v for k, v in self.values.items() if k not in RESERVED_VARS_KEYS}
