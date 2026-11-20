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
