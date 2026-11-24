import shutil
from pathlib import Path

import pytest

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "payments-service"


@pytest.fixture
def sandbox_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A disposable copy of the example, with HOME and state inside tmp_path."""
    project = tmp_path / "payments-service"
    shutil.copytree(EXAMPLE, project)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("ASAC_STATE_DIR", str(tmp_path / ".asac-state"))
    # The example's delegate steps declare a Docker runner; offline tests use the in-memory one.
    monkeypatch.setenv("ASAC_RUNNER", "fake")
    return project


def init_git(project: Path) -> None:
    """Make a test project a git repository with one commit (isolated runs need one)."""
    import subprocess

    def git(*args: str) -> None:
        subprocess.run(
            ["git", "-c", "user.email=t@t", "-c", "user.name=t", *args],
            cwd=project, check=True, capture_output=True,
        )  # fmt: skip

    git("init", "-q", "-b", "main")
    git("add", "-A")
    git("commit", "-q", "-m", "base")
