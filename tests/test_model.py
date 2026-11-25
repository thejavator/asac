from pathlib import Path

import pytest
from pydantic import ValidationError

from asac.loader import load_manifest, load_vars
from asac.model import RESERVED_VARS_KEYS, Manifest
from asac.model.manifest import HookDefinition


def test_example_manifest_loads(sandbox_project: Path) -> None:
    m = load_manifest(sandbox_project / "asac.yaml")
    assert m.asac.spec == "0.4"
    assert set(m.pipelines["feature"].steps) == {
        "requirements",
        "development",
        "verification",
        "release",
    }


def test_wrong_spec_version_rejected() -> None:
    with pytest.raises(ValidationError):
        Manifest.model_validate({"asac": {"spec": "1.0", "workspace": "x"}})


def test_unknown_key_rejected() -> None:
    with pytest.raises(ValidationError):
        Manifest.model_validate({"asac": {"spec": "0.4", "workspace": "x"}, "routing": {}})


def test_spec_level_bounds() -> None:
    base = {"asac": {"spec": "0.4", "workspace": "x"}}
    step = {"capability": "c", "agent": "a"}
    for bad in (0, 4):
        with pytest.raises(ValidationError):
            Manifest.model_validate(
                {**base, "pipelines": {"p": {"specLevel": bad, "steps": {"s": step}}}}
            )


@pytest.mark.parametrize("data", [{}, {"run": "a.sh", "ref": "r/x@1.0.0"}])
def test_hook_needs_exactly_one_source(data: dict[str, str]) -> None:
    with pytest.raises(ValidationError):
        HookDefinition.model_validate(data)


def test_reserved_vars_keys_are_not_user_values(sandbox_project: Path) -> None:
    v = load_vars(sandbox_project / "asac.vars.yaml.example")
    assert set(v.values) >= {"state_backend", "data_residency"}
    assert not RESERVED_VARS_KEYS & set(v.user_values())


def test_every_setting_the_engine_reads_from_the_values_file_is_reserved() -> None:
    """`asac vars diff` lists the keys no `var.*` uses. A setting ASAC itself reads from the values
    file (the runner, the sandbox, retries…) is not a stray key: reporting it as unused tells a
    person to delete a line that is in force."""
    read_by_the_engine = {
        "autorun", "autorun_timeout", "isolate", "notify_targets", "parallel", "retries",
        "sandbox", "sandbox_domains", "runner_kind", "runner_image", "runner_network",
        "runner_env", "runner_k8s_context", "runner_k8s_namespace", "runner_k8s_pvc",
        "runner_k8s_secret",
    }  # fmt: skip
    assert read_by_the_engine <= RESERVED_VARS_KEYS, read_by_the_engine - RESERVED_VARS_KEYS


def test_a_key_nothing_reads_is_still_reported_as_unused(tmp_path: Path) -> None:
    from typer.testing import CliRunner

    from asac.cli import app

    (tmp_path / "asac.yaml").write_text('asac: { spec: "0.4", workspace: w }\n')
    (tmp_path / "asac.vars.yaml").write_text("retries: 1\nleftover_from_last_year: x\n")
    r = CliRunner().invoke(app, ["vars", "diff", "-f", str(tmp_path / "asac.yaml")])
    assert "unused: leftover_from_last_year" in r.output
    assert "retries" not in r.output
