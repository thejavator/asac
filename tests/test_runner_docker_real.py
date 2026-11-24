"""The Docker runner against a real daemon. Skipped when Docker is not running."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from asac.adapters.runner_local import DEFAULT_IMAGE, DockerRunner

pytestmark = pytest.mark.integration
IMAGE = DEFAULT_IMAGE  # the image ASAC builds for delegated steps (F58)


def _ready() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        # A Docker daemon that is installed but stuck never answers: treat it as absent.
        if subprocess.run(["docker", "info"], capture_output=True, timeout=15).returncode != 0:
            return False
        probe = ["docker", "image", "inspect", IMAGE]
        return subprocess.run(probe, capture_output=True, timeout=15).returncode == 0
    except subprocess.TimeoutExpired:
        return False


@pytest.fixture
def worktree(tmp_path: Path) -> Path:
    """A run's folder, with a file in it; next to it, a main checkout the agent must never see."""
    work = tmp_path / "state" / "worktrees" / "itest"
    work.mkdir(parents=True)
    (work / "hello.txt").write_text("from the worktree", encoding="utf-8")
    main = tmp_path / "main"
    main.mkdir()
    (main / "asac.yaml").write_text("the rules\n", encoding="utf-8")
    (main / ".asac").mkdir()
    (main / ".asac" / "hook.sh").write_text("exit 0\n", encoding="utf-8")
    return work


@pytest.fixture
def runner(tmp_path: Path, worktree: Path) -> DockerRunner:
    if not _ready():
        pytest.skip(f"docker is not running or {IMAGE} is not built (see asac doctor)")
    return DockerRunner(
        tmp_path / "main",
        image=IMAGE,
        env={"ASAC_TEST_KEY": "sup3r-s3cret"},
        worktree_for=lambda run_id: worktree,
    )


def test_the_container_gets_the_worktree_and_nothing_else_of_the_host(
    runner: DockerRunner, worktree: Path, tmp_path: Path
) -> None:
    """F59.1, F59.2, F59.4: one writable folder; the rules and the state are not there."""
    handle = runner.start("itest", "step1")
    try:
        sh = lambda cmd: runner.exec(handle, ["sh", "-c", cmd], 30)  # noqa: E731
        assert sh("cat /work/hello.txt").stdout == "from the worktree"
        assert sh("echo made-in-the-container > /work/made.txt").exit_code == 0
        assert (worktree / "made.txt").read_text().strip() == "made-in-the-container"  # on the host
        for hidden in (str(tmp_path / "main"), str(tmp_path / "state"), "/project"):
            assert sh(f"ls {hidden}").exit_code != 0, hidden  # the main checkout is not mounted
        assert sh("ls /work/asac.yaml /work/.asac").exit_code != 0  # none in the worktree either
        mounts = sh("cat /proc/self/mountinfo | grep -c ' /work '").stdout.strip()
        assert mounts == "1"
    finally:
        runner.stop(handle)


def test_container_is_locked_down_and_output_is_redacted(
    runner: DockerRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    """F59.3 and F61: no privileges, no network, a read-only root, secrets masked."""
    monkeypatch.setenv("ASAC_TEST_KEY", "sup3r-s3cret")
    handle = runner.start("itest", "step1")
    try:
        sh = lambda cmd: runner.exec(handle, ["sh", "-c", cmd], 30)  # noqa: E731
        assert sh("touch /etc/new").exit_code != 0  # root filesystem is read-only
        assert sh("touch /tmp/ok").exit_code == 0  # the tool's scratch space is writable
        assert sh("id -u").stdout.strip() == "65534"  # not root
        assert sh("grep -E '^CapEff' /proc/self/status").stdout.split()[-1] == "0000000000000000"
        assert (
            sh(
                "node -e \"fetch('http://1.1.1.1').then(()=>console.log('up'),()=>console.log('offline'))\""
            )
            .stdout.strip()
            .endswith("offline")
        )  # no network
        leaked = sh("echo $ASAC_TEST_KEY")
        assert "sup3r-s3cret" not in leaked.stdout and "sup3r-s3cret" not in leaked.stderr
    finally:
        runner.stop(handle)
    names = subprocess.run(["docker", "ps", "-q", "--filter", f"id={handle}"], capture_output=True)
    assert names.stdout.strip() == b""  # stopped and removed


def test_a_run_without_a_worktree_never_gets_the_main_checkout(runner: DockerRunner) -> None:
    """F59.2: there is no fallback to the project folder."""
    runner.worktree_for = lambda run_id: None
    with pytest.raises(RuntimeError, match="no worktree"):
        runner.start("itest", "step1")


def test_timeout_returns_124(runner: DockerRunner) -> None:
    handle = runner.start("itest", "slow")
    try:
        res = runner.exec(handle, ["sleep", "30"], 1)
        assert res.exit_code == 124 and "timed out" in res.stderr
    finally:
        runner.stop(handle)
