"""Layer 2 model: ``asac.vars.yaml``. Values only, never structure."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

# Keys that configure the platform itself. They are not ``var.*`` values,
# so ``asac vars diff`` must never report them as unused.
RESERVED_VARS_KEYS: frozenset[str] = frozenset(
    {"state_backend", "data_residency", "autorun", "autorun_timeout", "notify_targets"}
)


class VarsFile(BaseModel):
    model_config = ConfigDict(extra="allow")

    @property
    def values(self) -> dict[str, Any]:
        return dict(self.model_extra or {})

    def user_values(self) -> dict[str, Any]:
        return {k: v for k, v in self.values.items() if k not in RESERVED_VARS_KEYS}
