"""The rules an agent is judged by must be the same after it ran as before."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from asac.cli import app
from asac.engine.integrity import changed, snapshot
from tests.conftest import init_git

runner = CliRunner()
EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "real-tools"


def _tree(tmp_path: Path) -> Path:
    root = tmp_path / "p"
    (root / ".asac" / "hooks").mkdir(parents=True)
    (root / ".asac" / "hooks" / "a.sh").write_text("exit 0\n")
    (root / "asac.yaml").write_text("x: 1\n")
    (root / "app").mkdir()
    (root / "app" / "code.py").write_text("print(1)\n")
    return root


def test_snapshot_covers_the_manifest_vars_and_the_asac_folder(tmp_path: Path) -> None:
    root = _tree(tmp_path)
    (root / "asac.vars.yaml").write_text("tool: claude-code\n")
    snap = snapshot(root)
    assert set(snap) == {"asac.yaml", "asac.vars.yaml", ".asac/hooks/a.sh"}


def test_application_code_is_not_a_protected_rule(tmp_path: Path) -> None:
    root = _tree(tmp_path)
    before = snapshot(root)
    (root / "app" / "code.py").write_text("print(2)\n")  # that is the agent's job
    assert changed(before, snapshot(root)) == []


@pytest.mark.parametrize("what", ["edit", "delete", "add"])
def test_any_change_to_a_rule_is_reported(tmp_path: Path, what: str) -> None:
    root = _tree(tmp_path)
    before = snapshot(root)
    if what == "edit":
        (root / ".asac" / "hooks" / "a.sh").write_text("exit 1\n")
    elif what == "delete":
        (root / ".asac" / "hooks" / "a.sh").unlink()
    else:
        (root / ".asac" / "hooks" / "b.sh").write_text("exit 0\n")
    assert changed(before, snapshot(root)) != []


def test_symlinks_are_not_followed_out_of_the_tree(tmp_path: Path) -> None:
    root = _tree(tmp_path)
    outside = tmp_path / "secret.txt"
    outside.write_text("s")
    (root / ".asac" / "link").symlink_to(outside)
    assert ".asac/link" in snapshot(root)  # recorded as a link, its target is not read
    outside.write_text("changed")
    assert changed(snapshot(root), snapshot(root)) == []


# -- engine ----------------------------------------------------------------------------------


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "proj"
    shutil.copytree(EXAMPLE, root)
    shutil.copy(root / "vars" / "claude-code.yaml", root / "asac.vars.yaml")
    init_git(root)
    bindir = tmp_path / "bin"
    bindir.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("ASAC_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("ASAC_FIXED_TIME", "2026-01-01T00:00:00Z")
    monkeypatch.setenv("ASAC_AUTORUN", "1")
    monkeypatch.setenv("ASAC_SANDBOX", "0")  # no sandbox: only the integrity check can notice
    monkeypatch.setenv("PATH", f"{bindir}:/usr/bin:/bin")
    return root


def _tool(tmp_path: Path, body: str) -> None:
    exe = tmp_path / "bin" / "claude"
    exe.write_text(
        "#!/bin/sh\n" + body + "\n"
        'echo \'{"type":"result","is_error":false,"total_cost_usd":0.01,'
        '"usage":{},"result":"x"}\'\n'
    )
    exe.chmod(0o755)


def test_a_tool_that_edits_a_hook_blocks_the_step_and_is_audited(
    project: Path, tmp_path: Path
) -> None:
    hook = project / ".asac" / "hooks" / "tests-green.sh"
    _tool(
        tmp_path,
        f'echo "exit 0" > "{hook}"; printf "# Spec\\n## Acceptance criteria\\n- ok\\n" > SPEC.md',
    )
    r = runner.invoke(
        app, ["apply", "-p", "feature", "--run-id", "i1", "-f", str(project / "asac.yaml")]
    )
    assert r.exit_code == 3, r.output
    log = runner.invoke(app, ["logs", "i1", "-f", str(project / "asac.yaml")]).output
    assert "integrity.violated requirements" in log and ".asac/hooks/tests-green.sh" in log
    assert "step.completed requirements" not in log
    assert "gate.opened" not in log  # a tampered run never reaches a human as if it were clean


def test_a_clean_run_records_that_the_rules_were_verified(project: Path, tmp_path: Path) -> None:
    _tool(tmp_path, 'printf "# Spec\\n## Acceptance criteria\\n- ok\\n" > SPEC.md')
    r = runner.invoke(
        app, ["apply", "-p", "feature", "--run-id", "i2", "-f", str(project / "asac.yaml")]
    )
    assert r.exit_code == 2, r.output
    log = runner.invoke(app, ["logs", "i2", "-f", str(project / "asac.yaml")]).output
    assert "integrity.verified requirements" in log
