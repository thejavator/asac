"""F66.5: the templates travel in the wheel; `asac init` works with only the wheel installed.

Builds the wheel, installs it alone in a new virtual environment and runs `asac init` there, so a
template left out of the package (or read from the source tree) cannot pass unnoticed.
"""

from __future__ import annotations

import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(shutil.which("uv") is None, reason="uv is needed to build and install"),
]

TEMPLATE_FILES = {
    "asac.yaml",
    "asac.vars.yaml.example",
    ".asac/skills/spec.md",
    ".asac/skills/impl.md",
    ".asac/instructions/style.md",
    ".asac/hooks/no-secrets.sh",
    ".asac/hooks/spec-present.sh",
    ".asac/hooks/tests-green.sh",
}


def _run(*cmd: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=240)


@pytest.fixture(scope="module")
def wheel(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("wheel")
    built = _run("uv", "build", "--wheel", "--out-dir", str(out), str(ROOT))
    assert built.returncode == 0, built.stderr
    (found,) = out.glob("*.whl")
    return found


def test_the_wheel_contains_every_template_file(wheel: Path) -> None:
    with zipfile.ZipFile(wheel) as z:
        names = {n for n in z.namelist() if n.startswith("asac/templates/feature/")}
    assert {n.removeprefix("asac/templates/feature/") for n in names} == TEMPLATE_FILES


def test_init_works_in_a_clean_environment_with_only_the_wheel(wheel: Path, tmp_path: Path) -> None:
    venv = tmp_path / "venv"
    assert _run("uv", "venv", "-q", str(venv)).returncode == 0
    python = venv / "bin" / "python"
    installed = _run("uv", "pip", "install", "-q", "--python", str(python), str(wheel))
    assert installed.returncode == 0, installed.stderr
    project = tmp_path / "project"
    asac = venv / "bin" / "asac"
    init = _run(str(asac), "init", str(project), "--template", "feature", cwd=tmp_path)
    assert init.returncode == 0, init.stderr
    made = {
        p.relative_to(project).as_posix()
        for p in project.rglob("*")
        if p.is_file() and p.name != ".gitignore"
    }
    assert made == TEMPLATE_FILES
    assert (project / ".asac/hooks/tests-green.sh").stat().st_mode & 0o111  # still executable
    checked = _run(str(asac), "validate", "-f", str(project / "asac.yaml"), cwd=tmp_path)
    assert checked.returncode == 0 and "0 error(s), 0 warning(s)" in checked.stdout
