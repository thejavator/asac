"""Conformance suite for the Forge port. Every adapter must pass it."""

import subprocess
from pathlib import Path

import httpx
import pytest

from asac.adapters.forge_git import GitForge
from asac.adapters.forge_http import GitHubForge, GitLabForge
from asac.adapters.forge_more import AzureDevOpsForge, BitbucketForge, GiteaForge
from asac.ports.forge import (
    Author,
    Conflict,
    Forge,
    ForgeError,
    NotFound,
    Unsupported,
)
from tests.conformance.fake_forges import Repo, azure, bitbucket, gitea, github, gitlab

ALICE = Author("Alice", "alice@example.com")


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@e.x", *args],
        cwd=cwd, check=True, capture_output=True,
    )  # fmt: skip


@pytest.fixture(params=["git", "github", "gitlab", "gitea", "bitbucket", "azure"])
def forge(request: pytest.FixtureRequest, tmp_path: Path) -> Forge:
    if request.param == "github":
        return GitHubForge("o/r", "tok", "https://api.test",
                           httpx.Client(transport=github(Repo())))  # fmt: skip
    if request.param == "gitlab":
        return GitLabForge("g/r", "tok", "https://gl.test/api/v4",
                           httpx.Client(transport=gitlab(Repo())))  # fmt: skip
    if request.param == "gitea":
        return GiteaForge("o/r", "tok", "https://g.test/api/v1",
                          httpx.Client(transport=gitea(Repo())))  # fmt: skip
    if request.param == "bitbucket":
        return BitbucketForge("w/r", "tok", "https://bb.test/2.0",
                              httpx.Client(transport=bitbucket(Repo())))  # fmt: skip
    if request.param == "azure":
        return AzureDevOpsForge("org/proj/r", "tok", "https://az.test",
                                httpx.Client(transport=azure(Repo())))  # fmt: skip
    seed = tmp_path / "seed"
    seed.mkdir()
    _git(seed, "init", "-q", "-b", "main")
    (seed / "asac.yaml").write_text("version: 1\n")
    _git(seed, "add", ".")
    _git(seed, "commit", "-q", "-m", "init")
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "clone", "-q", "--bare", str(seed), str(remote)], check=True)
    return GitForge(str(remote), tmp_path / "cache")


def test_default_branch_and_read(forge: Forge) -> None:
    assert forge.default_branch() == "main"
    f = forge.read_file("asac.yaml")
    assert f.content == "version: 1\n" and len(f.commit) == 40  # bytes kept exactly


def test_read_missing_file_and_branch(forge: Forge) -> None:
    with pytest.raises(NotFound):
        forge.read_file("nope.yaml")
    with pytest.raises(NotFound):
        forge.read_file("asac.yaml", "ghost")


@pytest.mark.parametrize("bad", ["../x", "/etc/passwd", "a/../../b", ""])
def test_unsafe_paths_refused(forge: Forge, bad: str) -> None:
    with pytest.raises(ForgeError):
        forge.read_file(bad)


@pytest.mark.parametrize("bad", ["-x", "a..b", "x.lock", "a b", "x/"])
def test_unsafe_branch_names_refused(forge: Forge, bad: str) -> None:
    with pytest.raises(ForgeError):
        forge.create_branch(bad, forge.head("main"))


def test_branch_commit_roundtrip_and_author(forge: Forge, tmp_path: Path) -> None:
    base = forge.head("main")
    forge.create_branch("asac/pipeline-1", base)
    new = forge.commit_files(
        "asac/pipeline-1", {"asac.yaml": "version: 2\n"}, "Change the pipeline", ALICE, base
    )
    assert new != base and forge.head("asac/pipeline-1") == new
    assert forge.read_file("asac.yaml", "asac/pipeline-1").content.strip() == "version: 2"
    assert forge.read_file("asac.yaml").content.strip() == "version: 1"  # main untouched
    if not isinstance(forge, GitForge):
        return
    log = subprocess.run(
        ["git", "--git-dir", str(tmp_path / "remote.git"), "log", "-1", "--format=%an <%ae>|%B",
         "asac/pipeline-1"], capture_output=True, text=True, check=True,
    ).stdout  # fmt: skip
    assert log.startswith("Alice <alice@example.com>|") and "on behalf of Alice" in log


def test_stale_base_is_a_conflict_and_never_overwrites(forge: Forge) -> None:
    base = forge.head("main")
    forge.create_branch("b1", base)
    first = forge.commit_files("b1", {"asac.yaml": "v: 2\n"}, "one", ALICE, base)
    with pytest.raises(Conflict) as err:
        forge.commit_files("b1", {"asac.yaml": "v: 3\n"}, "two", ALICE, base)
    assert err.value.current_sha == first
    assert forge.read_file("asac.yaml", "b1").content.strip() == "v: 2"


def test_existing_branch_is_not_recreated(forge: Forge) -> None:
    base = forge.head("main")
    forge.create_branch("b2", base)
    with pytest.raises(ForgeError):
        forge.create_branch("b2", base)


def test_capabilities_match_behaviour(forge: Forge) -> None:
    if not forge.capabilities().change_requests:
        with pytest.raises(Unsupported):
            forge.open_change_request("a", "main", "t", "d")


def test_change_request_roundtrip(forge: Forge) -> None:
    if not forge.capabilities().change_requests:
        pytest.skip("adapter has no change requests")
    base = forge.head("main")
    forge.create_branch("asac/pipeline-9", base)
    forge.commit_files("asac/pipeline-9", {"asac.yaml": "v: 9\n"}, "x", ALICE, base)
    cr = forge.open_change_request("asac/pipeline-9", "main", "Pipeline change", "why")
    got = forge.get_change_request(cr.id)
    assert got.source_branch == "asac/pipeline-9" and got.target_branch == "main"
    assert got.state == "open" and got.url.startswith("https://")
    with pytest.raises(NotFound):
        forge.get_change_request("999")


def test_token_never_in_errors() -> None:
    bad = GitHubForge("o/r", "wrong-token-123", "https://api.test",
                      httpx.Client(transport=github(Repo())))  # fmt: skip
    with pytest.raises(ForgeError) as err:
        bad.default_branch()
    assert "wrong-token-123" not in str(err.value)


@pytest.mark.parametrize(
    "make",
    [
        lambda c: GiteaForge("o/r", "wrong-token-123", "https://g.test/api/v1", c),
        lambda c: BitbucketForge("w/r", "wrong-token-123", "https://bb.test/2.0", c),
        lambda c: AzureDevOpsForge("org/proj/r", "wrong-token-123", "https://az.test", c),
    ],
)
def test_token_never_in_errors_other_forges(make: object) -> None:
    c = httpx.Client(transport=httpx.MockTransport(lambda _r: httpx.Response(401, json={})))
    with pytest.raises(ForgeError) as err:
        make(c).default_branch()  # type: ignore[operator]
    assert "wrong-token-123" not in str(err.value)
