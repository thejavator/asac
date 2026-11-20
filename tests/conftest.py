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
    return project
