"""``VarsStore`` on the ``asac.vars.yaml`` file next to the manifest.

Writes are atomic (temp file + rename). Comments are not kept: the file is regenerated with
a header, keys in their original order.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

import yaml

from asac.ports.vars import VAULT_REF, Variable, VarsError, check

HEADER = "# Layer 2 variables. Managed by ASAC; secrets are vault references only.\n"


class FileVarsStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def _read(self) -> dict[str, Any]:
        if not self.path.is_file():
            return {}
        try:
            raw = yaml.safe_load(self.path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            raise VarsError(f"invalid {self.path.name}: {exc}") from None
        if not isinstance(raw, dict):
            raise VarsError(f"{self.path.name} must be a mapping")
        return raw

    def _write(self, data: dict[str, Any]) -> None:
        text = HEADER + yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".vars-", suffix=".yaml")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(text)
            os.replace(tmp, self.path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise

    def list(self) -> list[Variable]:
        out = []
        for k, v in self._read().items():
            value = "" if v is None else str(v)
            out.append(Variable(str(k), value, bool(VAULT_REF.match(value))))
        return out

    def set(self, key: str, value: str) -> Variable:
        var = check(key, value)
        data = self._read()
        data[key] = var.value
        self._write(data)
        return var

    def delete(self, key: str) -> None:
        data = self._read()
        if key not in data:
            raise VarsError(f"unknown variable '{key}'")
        del data[key]
        self._write(data)
