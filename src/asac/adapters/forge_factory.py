"""Build a Forge for a project from its variables (``forge_kind``, ``forge_repo``, ``forge_token``).

The token is a vault reference. This resolver reads it from the environment variable
``ASAC_VAULT_<PATH>`` (path upper-cased, non-alphanumerics become ``_``); a real vault client
replaces ``resolve_vault`` without touching the callers.
"""

from __future__ import annotations

from pathlib import Path

from asac.adapters.forge_git import GitForge
from asac.adapters.forge_http import GitHubForge, GitLabForge
from asac.adapters.forge_more import AzureDevOpsForge, BitbucketForge, GiteaForge
from asac.adapters.vault import VaultError
from asac.adapters.vault import resolve_vault as _resolve
from asac.ports.forge import Forge, ForgeError
from asac.ports.vars import VarsError, VarsStore


def resolve_vault(ref: str) -> str:
    try:
        return _resolve(ref, "the forge token")
    except VaultError as exc:
        raise ForgeError(str(exc)) from None


def forge_from_vars(store: VarsStore, cache: Path) -> Forge | None:
    try:
        v = {x.key: x.value for x in store.list()}
    except VarsError:
        return None
    kind = v.get("forge_kind")
    if not kind:
        return None
    repo = v.get("forge_repo", "")
    api = v.get("forge_api") or None
    if kind == "git":
        return GitForge(repo, cache)
    token = resolve_vault(v.get("forge_token", ""))
    if api and not api.startswith("https://"):
        raise ForgeError("forge_api must be an https URL")
    if kind == "github":
        return GitHubForge(repo, token, api or "https://api.github.com")
    if kind == "gitlab":
        return GitLabForge(repo, token, api or "https://gitlab.com/api/v4")
    if kind in ("gitea", "forgejo"):
        if not api:
            raise ForgeError("forge_api is required for gitea and forgejo (https://host/api/v1)")
        return GiteaForge(repo, token, api)
    if kind == "bitbucket":
        return BitbucketForge(repo, token, api or "https://api.bitbucket.org/2.0")
    if kind == "azure_devops":
        return AzureDevOpsForge(repo, token, api or "https://dev.azure.com")
    raise ForgeError(f"unknown forge_kind '{kind}'")
