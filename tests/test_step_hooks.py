"""Hooks per step: global hooks first, then the step's own. tests-green skips requirements."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from asac.cli import app
from asac.engine.runtime import store_for
from asac.hooks import hooks_for
from asac.loader.load import load_manifest
from asac.model.manifest import Step
from tests.conftest import init_git

runner = CliRunner()
EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "real-tools"


def test_a_step_accepts_its_own_hooks() -> None:
    s = Step(capability="c", agent="a", hooks={"post_step": ["tests-green"]})
    assert s.hooks is not None and s.hooks.post_step == ["tests-green"] and s.hooks.pre_tool == []


def test_a_step_hooks_block_holds_only_attachments_not_definitions() -> None:
    """Scripts are declared once, globally: a step only says which ones it runs."""
    with pytest.raises(ValidationError):
        Step(capability="c", agent="a", hooks={"definitions": {"x": {"run": "x.sh"}}})


def test_global_hooks_run_first_then_the_step_hooks_without_duplicates() -> None:
    m = load_manifest(EXAMPLE / "asac.yaml")
    m.hooks.pre_tool = ["no-secrets"]  # type: ignore[union-attr]
    step = m.pipelines["feature"].steps["requirements"]
    step.hooks = (
        type(step)
        .model_validate(
            {"capability": "c", "agent": "a", "hooks": {"pre_tool": ["step-scope", "no-secrets"]}}
        )
        .hooks
    )
    assert hooks_for(m, step, "pre_tool") == ["no-secrets", "step-scope"]


def test_validate_names_an_unknown_step_hook(tmp_path: Path) -> None:
    root = tmp_path / "p"
    shutil.copytree(EXAMPLE, root, ignore=shutil.ignore_patterns(".DS_Store", ".asac-state"))
    text = (
        (root / "asac.yaml")
        .read_text()
        .replace(
            "        hooks: { post_step: [tests-green] }\n",
            "        hooks: { post_step: [tests-green, nope] }\n",
            1,
        )
    )
    (root / "asac.yaml").write_text(text)
    r = runner.invoke(app, ["validate", "-f", str(root / "asac.yaml")])
    assert r.exit_code == 1 and "ASAC012" in r.output and "nope" in r.output


# -- the real-tools example, moved to per-step hooks ---------------------------------------------


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "rt"
    shutil.copytree(EXAMPLE, root, ignore=shutil.ignore_patterns(".DS_Store", ".asac-state"))
    shutil.copy(root / "vars" / "claude-code.yaml", root / "asac.vars.yaml")
    init_git(root)
    bindir = tmp_path / "bin"
    bindir.mkdir()
    (bindir / "claude").write_text(
        "#!/bin/sh\n"
        'printf "# Spec\\n## Acceptance criteria\\n- ok\\n" > SPEC.md\n'
        'echo \'{"type":"result","is_error":false,"total_cost_usd":0.01,'
        '"usage":{},"result":"x"}\'\n'
    )
    (bindir / "claude").chmod(0o755)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("ASAC_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("ASAC_FIXED_TIME", "2026-01-01T00:00:00Z")
    monkeypatch.setenv("ASAC_AUTORUN", "1")
    monkeypatch.setenv("ASAC_SANDBOX", "0")
    monkeypatch.setenv("PATH", f"{bindir}:/usr/bin:/bin")
    return root


def _hooks_of(project: Path, run_id: str, step: str) -> list[str]:
    return [
        a.detail.split("\n", 1)[0]
        for a in store_for(project / "asac.yaml").audit(run_id)
        if a.action in ("hook.passed", "hook.failed") and a.step_id == step
    ]


def test_requirements_runs_no_test_hook(project: Path) -> None:
    runner.invoke(
        app, ["apply", "-p", "feature", "--run-id", "h1", "-f", str(project / "asac.yaml")]
    )
    ran = _hooks_of(project, "h1", "requirements")
    assert "post_step tests-green" not in ran, ran
    assert ran == ["pre_tool no-secrets", "pre_tool step-scope", "post_step step-scope"], ran


def test_development_runs_the_test_hook_and_not_the_spec_hook(project: Path) -> None:
    f = str(project / "asac.yaml")
    runner.invoke(app, ["apply", "-p", "feature", "--run-id", "h2", "-f", f])
    runner.invoke(app, ["approve", "gate_h2_requirements", "--role", "product_owner",
                        "--by", "po", "-f", f])  # fmt: skip
    ran = _hooks_of(project, "h2", "development")
    assert "post_step tests-green" in ran, ran
    assert not any("step-scope" in h for h in ran), ran
    assert "pre_tool no-secrets" in ran  # the global hook still runs on every step


def test_the_example_scripts_no_longer_guard_themselves_by_step_name() -> None:
    for name in ("tests-green.sh", "step-scope.sh"):
        text = (EXAMPLE / ".asac" / "hooks" / name).read_text()
        assert '"$ASAC_STEP" =' not in text and "ASAC_STEP:-" not in text, name


def test_a_duplicated_key_is_refused_instead_of_silently_overwriting(tmp_path: Path) -> None:
    """Writing `hooks:` twice under a step used to keep only the last one, dropping a check."""
    root = tmp_path / "p"
    shutil.copytree(EXAMPLE, root, ignore=shutil.ignore_patterns(".DS_Store", ".asac-state"))
    text = (
        (root / "asac.yaml")
        .read_text()
        .replace(
            "        hooks: { post_step: [tests-green] }\n",
            "        hooks: { post_step: [tests-green] }\n        hooks: { post_step: [] }\n",
            1,
        )
    )
    (root / "asac.yaml").write_text(text)
    r = runner.invoke(app, ["validate", "-f", str(root / "asac.yaml")])
    assert r.exit_code == 1, r.output
    assert "duplicate" in r.output.lower() and "hooks" in r.output
