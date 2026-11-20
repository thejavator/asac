"""Wiring from project variables: forge, tracker, wiki, runner, state backend, URL probe."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from asac.adapters import AdapterNotAvailable, open_state
from asac.adapters.forge_factory import forge_from_vars
from asac.adapters.forge_git import GitForge
from asac.adapters.forge_http import GitHubForge, GitLabForge
from asac.adapters.forge_more import AzureDevOpsForge, BitbucketForge, GiteaForge
from asac.adapters.links_factory import tracker_from_vars, wiki_from_vars
from asac.adapters.runner_local import DockerRunner, runner_from_vars
from asac.adapters.state_sqlite import SqliteStateStore
from asac.adapters.vars_file import FileVarsStore
from asac.portal import probe
from asac.ports.forge import ForgeError
from asac.ports.tracker import TrackerError
from asac.ports.wiki import WikiError


def vars_of(tmp_path: Path, **kv: str) -> FileVarsStore:
    store = FileVarsStore(tmp_path / "asac.vars.yaml")
    for k, v in kv.items():
        store.set(k, v)
    return store


@pytest.fixture(autouse=True)
def token(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("FORGE_TOKEN", "TRACKER_TOKEN", "WIKI_TOKEN"):
        monkeypatch.setenv(f"ASAC_VAULT_{name}", "s3cr3t")


@pytest.mark.parametrize(
    ("kind", "repo", "api", "cls"),
    [
        ("github", "o/n", "", GitHubForge),
        ("gitlab", "o/n", "", GitLabForge),
        ("gitea", "o/n", "https://h/api/v1", GiteaForge),
        ("forgejo", "o/n", "https://h/api/v1", GiteaForge),
        ("bitbucket", "w/s", "", BitbucketForge),
        ("azure_devops", "o/p/r", "", AzureDevOpsForge),
    ],
)
def test_forge_kinds(tmp_path: Path, kind: str, repo: str, api: str, cls: type) -> None:
    kv = {"forge_kind": kind, "forge_repo": repo, "forge_token": "${vault.forge/token}"}
    if api:
        kv["forge_api"] = api
    assert isinstance(forge_from_vars(vars_of(tmp_path, **kv), tmp_path / "c"), cls)


def test_forge_none_git_and_errors(tmp_path: Path) -> None:
    assert forge_from_vars(vars_of(tmp_path), tmp_path / "c") is None
    git = vars_of(tmp_path, forge_kind="git", forge_repo=str(tmp_path))
    assert isinstance(forge_from_vars(git, tmp_path / "c"), GitForge)
    tok = "${vault.forge/token}"
    for kv, text in [
        ({"forge_kind": "gitea", "forge_repo": "o/n"}, "forge_api is required"),
        ({"forge_kind": "github", "forge_api": "http://x"}, "https"),
        ({"forge_kind": "svn"}, "unknown forge_kind"),
    ]:
        s = FileVarsStore(tmp_path / f"{text[:4]}.yaml")
        for k, v in {**kv, "forge_token": tok}.items():
            s.set(k, v)
        with pytest.raises(ForgeError, match=text):
            forge_from_vars(s, tmp_path / "c")


def test_vars_store_refuses_a_plain_secret(tmp_path: Path) -> None:
    from asac.ports.vars import VarsError

    with pytest.raises(VarsError) as exc:
        vars_of(tmp_path, forge_token="plain-secret")
    assert "plain-secret" not in str(exc.value)


def test_tracker_and_wiki_factories(tmp_path: Path) -> None:
    ref = "${vault.tracker/token}"
    assert tracker_from_vars(vars_of(tmp_path)) is None
    for kind, extra in [("jira", {"tracker_url": "https://j"}), ("github", {}), ("gitlab", {})]:
        s = FileVarsStore(tmp_path / f"t-{kind}.yaml")
        for k, v in {
            "tracker_kind": kind,
            "tracker_token": ref,
            "tracker_project": "o/n",
            **extra,
        }.items():
            s.set(k, v)
        assert tracker_from_vars(s) is not None
    bad = vars_of(tmp_path, tracker_kind="jira", tracker_url="http://j", tracker_token=ref)
    with pytest.raises(TrackerError, match="https"):
        tracker_from_vars(bad)
    with pytest.raises(TrackerError, match="unknown"):
        tracker_from_vars(
            vars_of(tmp_path / "x" if False else tmp_path, tracker_kind="svn", tracker_token=ref)
        )

    w = "${vault.wiki/token}"
    d = tmp_path / "w"
    d.mkdir()
    assert wiki_from_vars(FileVarsStore(d / "v.yaml")) is None
    conf = FileVarsStore(d / "c.yaml")
    for k, v in {"wiki_kind": "confluence", "wiki_url": "https://c/wiki", "wiki_space": "PAY",
                 "wiki_token": w}.items():  # fmt: skip
        conf.set(k, v)
    assert wiki_from_vars(conf) is not None
    gl = FileVarsStore(d / "g.yaml")
    for k, v in {"wiki_kind": "gitlab", "wiki_project": "o/n", "wiki_token": w}.items():
        gl.set(k, v)
    assert wiki_from_vars(gl) is not None
    bad_w = FileVarsStore(d / "b.yaml")
    for k, v in {"wiki_kind": "notion", "wiki_token": w}.items():
        bad_w.set(k, v)
    with pytest.raises(WikiError, match="unknown"):
        wiki_from_vars(bad_w)


def test_missing_vault_value_is_reported_without_secret(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("ASAC_VAULT_TRACKER_TOKEN")
    s = vars_of(tmp_path, tracker_kind="github", tracker_token="${vault.tracker/token}")
    with pytest.raises(TrackerError, match="not available"):
        tracker_from_vars(s)


def test_docker_runner_calls(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []
    results = {"returncode": 0}

    def fake(cmd: list[str], **kw: Any) -> subprocess.CompletedProcess[str]:
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, results["returncode"], "cid\n", "err")

    monkeypatch.setattr(subprocess, "run", fake)
    r = DockerRunner(tmp_path, docker="/usr/bin/docker", env={"API_KEY": "k"})
    assert r.available()
    assert r.start("run1", "s1") == "cid"
    res = r.exec("cid", ["echo", "hi"], 5)
    assert res.exit_code == 0
    assert "docker" in calls[-1][0] and calls[-1][1:3] == ["exec", "cid"]
    r.stop("cid")
    assert calls[-1][1:3] == ["rm", "-f"] or "cid" in calls[-1]
    results["returncode"] = 1
    assert not r.available()
    with pytest.raises(RuntimeError, match="docker run failed"):
        r.start("run1", "s1")


def test_docker_runner_unavailable_and_timeout(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import shutil

    monkeypatch.setattr(shutil, "which", lambda name: None)
    assert not DockerRunner(tmp_path).available()

    def boom(cmd: list[str], **kw: Any) -> Any:
        raise subprocess.TimeoutExpired(cmd, 1, output=b"partial")

    monkeypatch.setattr(subprocess, "run", boom)
    r = DockerRunner(tmp_path, docker="/usr/bin/docker")
    assert not r.available()
    res = r.exec("cid", ["sleep", "9"], 1)
    assert res.exit_code == 124 and "timed out" in res.stderr


def test_runner_from_vars_docker_and_none(tmp_path: Path) -> None:
    assert runner_from_vars(tmp_path, {}) is None
    r = runner_from_vars(tmp_path, {"runner_kind": "docker", "runner_image": "img:1"})
    assert isinstance(r, DockerRunner) and r.image == "img:1"


def test_state_backend_choice(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ASAC_STATE_URL", raising=False)
    monkeypatch.setenv("ASAC_STATE_DIR", str(tmp_path / "st"))
    assert isinstance(open_state(tmp_path), SqliteStateStore)
    assert (tmp_path / "st" / "state.db").exists()
    open_state(tmp_path, "pay").close()
    assert (tmp_path / "st" / "pay" / "state.db").exists()
    monkeypatch.setenv("ASAC_STATE_URL", "mysql://x")
    with pytest.raises(AdapterNotAvailable, match="postgresql"):
        open_state(tmp_path)


def test_probe_refuses_private_and_bad_urls() -> None:
    assert probe.probe_url("ftp://x")[0] is False
    ok, msg = probe.probe_url("http://127.0.0.1:1/")
    assert not ok and "private" in msg
    assert not probe.probe_url("http://169.254.169.254/")[0]


def test_probe_reports_http_outcomes(monkeypatch: pytest.MonkeyPatch) -> None:
    import httpx

    monkeypatch.setattr(probe, "_blocked", lambda host: False)

    def head(status: int | Exception):  # type: ignore[no-untyped-def]
        def f(url: str, **kw: Any) -> httpx.Response:
            if isinstance(status, Exception):
                raise status
            return httpx.Response(status)

        return f

    monkeypatch.setattr(httpx, "head", head(200))
    assert probe.probe_url("https://example.org") == (True, "Reachable (HTTP 200).")
    monkeypatch.setattr(httpx, "head", head(503))
    assert not probe.probe_url("https://example.org")[0]
    monkeypatch.setattr(httpx, "head", head(httpx.ConnectError("x")))
    assert "Cannot connect" in probe.probe_url("https://example.org")[1]
    monkeypatch.setattr(httpx, "head", head(httpx.ReadTimeout("x")))
    assert "5 seconds" in probe.probe_url("https://example.org")[1]
    monkeypatch.setattr(httpx, "head", head(httpx.DecodingError("x")))
    assert "Request failed" in probe.probe_url("https://example.org")[1]
