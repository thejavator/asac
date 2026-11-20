"""Port for a project's layer-2 variables (``asac.vars.yaml``): URLs, choices, secret refs.

Secrets are never stored: a secret variable holds a ``${vault.path}`` reference that is
resolved at run time. The store refuses a literal value for a key that names a secret.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

VAULT_REF = re.compile(r"^\$\{vault\.[A-Za-z0-9_./-]+\}$")
SECRET_KEY = re.compile(r"(token|secret|password|passwd|api_?key|credential)", re.I)
KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")


class VarsError(Exception):
    pass


@dataclass(frozen=True)
class Variable:
    key: str
    value: str
    secret: bool  # True: value is a vault reference, safe to display


class VarsStore(Protocol):
    def list(self) -> list[Variable]: ...
    def set(self, key: str, value: str) -> Variable: ...
    def delete(self, key: str) -> None: ...


def check(key: str, value: str) -> Variable:
    """Shared rules for every adapter."""
    if not KEY.match(key):
        raise VarsError(f"invalid key '{key}': letters, digits and _, starting with a letter")
    value = value.strip()
    if len(value) > 2000 or "\n" in value:
        raise VarsError(f"value of '{key}' must be one line of at most 2000 characters")
    is_ref = bool(VAULT_REF.match(value))
    if SECRET_KEY.search(key) and not is_ref:
        raise VarsError(
            f"'{key}' names a secret: store a vault reference such as ${{vault.team/{key}}}, "
            "never the secret itself"
        )
    if value.startswith("${") and not is_ref:
        raise VarsError(f"'{value}' is not a valid vault reference")
    return Variable(key, value, is_ref)
