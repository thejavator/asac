"""A key `validate` accepts is either applied or reported. Never accepted and silently ignored."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from asac.cli import app

runner = CliRunner()
EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "real-tools"


def _project(tmp_path: Path, edit) -> Path:  # type: ignore[no-untyped-def]
    root = tmp_path / "p"
    shutil.copytree(EXAMPLE, root, ignore=shutil.ignore_patterns(".DS_Store", ".asac-state"))
    doc = yaml.safe_load((root / "asac.yaml").read_text())
    edit(doc)
    (root / "asac.yaml").write_text(yaml.safe_dump(doc, sort_keys=False))
    return root


def _validate(root: Path):  # type: ignore[no-untyped-def]
    return runner.invoke(app, ["validate", "-f", str(root / "asac.yaml")])


def _warned(out: str, where: str) -> bool:
    return any("ASAC027" in line and where in line for line in out.splitlines())


def test_a_clean_manifest_has_no_unapplied_warning(tmp_path: Path) -> None:
    r = _validate(_project(tmp_path, lambda d: None))
    assert r.exit_code == 0 and "ASAC027" not in r.output, r.output


def test_knowledge_is_reported_as_not_applied(tmp_path: Path) -> None:
    def add(d: dict) -> None:  # type: ignore[type-arg]
        d["knowledge"] = {"glossary": {"provider": "okf", "path": ".asac/instructions"}}

    r = _validate(_project(tmp_path, add))
    assert r.exit_code == 0, r.output  # a warning, not an error: the manifest stays valid
    assert _warned(r.output, "knowledge.glossary"), r.output
    assert "not applied" in r.output


def test_an_agent_knowledge_reference_is_reported_too(tmp_path: Path) -> None:
    def add(d: dict) -> None:  # type: ignore[type-arg]
        d["knowledge"] = {"g": {"provider": "okf", "path": ".asac/instructions"}}
        d["agents"]["analyst"]["knowledge"] = ["g"]

    assert _warned(_validate(_project(tmp_path, add)).output, "agents.analyst.knowledge")


def test_a_model_in_the_provider_config_is_reported_as_not_applied(tmp_path: Path) -> None:
    """The chosen model never reaches the tool: say so instead of letting someone believe it."""

    def add(d: dict) -> None:  # type: ignore[type-arg]
        d["providers"]["llm"]["config"] = {"model": "claude-opus-5-5"}

    r = _validate(_project(tmp_path, add))
    assert _warned(r.output, "providers.llm.config.model"), r.output
    assert "not applied" in r.output


def test_spec_level_is_reported_as_checked_only(tmp_path: Path) -> None:
    def add(d: dict) -> None:  # type: ignore[type-arg]
        d["pipelines"]["feature"]["specLevel"] = 1

    r = _validate(_project(tmp_path, add))
    assert _warned(r.output, "pipelines.feature.specLevel"), r.output
    assert "checked by validate only" in r.output


def test_the_warning_names_the_version_so_it_can_be_lifted_later(tmp_path: Path) -> None:
    def add(d: dict) -> None:  # type: ignore[type-arg]
        d["knowledge"] = {"g": {"provider": "okf", "path": ".asac/instructions"}}

    assert "0.1" in _validate(_project(tmp_path, add)).output


@pytest.mark.parametrize("key", ["knowledge"])
def test_every_unapplied_key_has_a_documented_reason(key: str) -> None:
    from asac.validate.unapplied import UNAPPLIED

    assert key in {u.key for u in UNAPPLIED}
    assert all(u.reason for u in UNAPPLIED)
