"""The Docker runner against a real daemon. Skipped when Docker is not running."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from asac.adapters.runner_local import DockerRunner

pytestmark = pytest.mark.integration
IMAGE = "postgres:16-alpine"  # already used by the Postgres conformance run; has sh and sleep


def _ready() -> bool:
    if shutil.which("docker") is None:
        return False
    if subprocess.run(["docker", "info"], capture_output=True).returncode != 0:
        return False
    return (
        subprocess.run(["docker", "image", "inspect", IMAGE], capture_output=True).returncode == 0
    )


@pytest.fixture
def runner(tmp_path: Path) -> DockerRunner:
    if not _ready():
        pytest.skip(f"docker is not running or {IMAGE} is not pulled")
    (tmp_path / "hello.txt").write_text("from the project", encoding="utf-8")
    return DockerRunner(tmp_path, image=IMAGE, env={"ASAC_TEST_KEY": "sup3r-s3cret"})


def test_container_is_locked_down_and_output_is_redacted(
    runner: DockerRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ASAC_TEST_KEY", "sup3r-s3cret")
    handle = runner.start("itest", "step1")
    try:
        sh = lambda cmd: runner.exec(handle, ["sh", "-c", cmd], 30)  # noqa: E731
        assert sh("cat /project/hello.txt").stdout == "from the project"
        assert sh("touch /project/new").exit_code != 0  # project is read-only
        assert sh("touch /etc/new").exit_code != 0  # root filesystem is read-only
        assert sh("touch /work/ok").exit_code == 0  # the scratch space is writable
        assert sh("id -u").stdout.strip() == "65534"  # not root
        assert (
            sh("wget -q -T 2 -O- http://1.1.1.1 || echo offline").stdout.strip().endswith("offline")
        )  # no network
        leaked = sh("echo $ASAC_TEST_KEY")
        assert "sup3r-s3cret" not in leaked.stdout and "sup3r-s3cret" not in leaked.stderr
    finally:
        runner.stop(handle)
    names = subprocess.run(["docker", "ps", "-q", "--filter", f"id={handle}"], capture_output=True)
    assert names.stdout.strip() == b""  # stopped and removed


def test_timeout_returns_124(runner: DockerRunner) -> None:
    handle = runner.start("itest", "slow")
    try:
        res = runner.exec(handle, ["sleep", "30"], 1)
        assert res.exit_code == 124 and "timed out" in res.stderr
    finally:
        runner.stop(handle)
