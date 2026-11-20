"""Resolve a ``${vault.path}`` reference to its secret value.

This resolver reads the environment variable ``ASAC_VAULT_<PATH>`` (path upper-cased,
non-alphanumerics become ``_``). A real vault client replaces this function without touching
the callers. The error message names the reference, never a value.
"""

from __future__ import annotations

import os
import re

from asac.ports.vars import VAULT_REF


class VaultError(Exception):
    pass


def env_name(ref: str) -> str:
    return "ASAC_VAULT_" + re.sub(r"[^A-Za-z0-9]", "_", ref[8:-1]).upper()


def resolve_vault(ref: str, what: str = "the token") -> str:
    if not VAULT_REF.match(ref):
        raise VaultError(f"{what} must be a vault reference")
    value = os.environ.get(env_name(ref))
    if not value:
        raise VaultError(f"vault reference {ref} is not available to the portal")
    return value
