"""Conformance suite for the VarsStore port."""

from pathlib import Path

import pytest

from asac.adapters.vars_file import FileVarsStore
from asac.ports.vars import VarsError, VarsStore


@pytest.fixture(params=["file"])
def store(request: pytest.FixtureRequest, tmp_path: Path) -> VarsStore:
    p = tmp_path / "asac.vars.yaml"
    p.write_text("jira_url: https://jira.example.com\njira_token: ${vault.jira/api-key}\n")
    return FileVarsStore(p)


def test_list_marks_vault_refs(store: VarsStore) -> None:
    got = {v.key: v for v in store.list()}
    assert got["jira_token"].secret and not got["jira_url"].secret


def test_set_and_delete(store: VarsStore) -> None:
    store.set("gitlab_url", "https://gitlab.example.com")
    assert "gitlab_url" in {v.key for v in store.list()}
    store.delete("gitlab_url")
    assert "gitlab_url" not in {v.key for v in store.list()}
    with pytest.raises(VarsError):
        store.delete("gitlab_url")


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("gitlab_token", "glpat-abcdef123456"),  # literal secret
        ("api_key", "sk-live-123"),
        ("x", "${vault.bad path}"),  # malformed ref
        ("bad key", "v"),
        ("multi", "a\nb"),
    ],
)
def test_refuses_unsafe_values(store: VarsStore, key: str, value: str) -> None:
    with pytest.raises(VarsError):
        store.set(key, value)


def test_secret_never_written(store: VarsStore, tmp_path: Path) -> None:
    with pytest.raises(VarsError):
        store.set("llm_api_key", "sk-ant-SECRET")
    assert "sk-ant-SECRET" not in (tmp_path / "asac.vars.yaml").read_text()
