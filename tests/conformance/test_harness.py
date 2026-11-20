"""Conformance suite for the Harness port, run against every registered adapter."""

from pathlib import Path

import pytest

from asac.adapters import HARNESS_ADAPTERS, AdapterContext
from asac.catalog import HARNESSES
from asac.loader.load import load_manifest

EXAMPLE = Path(__file__).resolve().parents[2] / "examples" / "payments-service"
PORT_METHODS = ("mount", "run", "tools", "permissions", "emit", "describe", "health_check")


@pytest.fixture(params=sorted(HARNESS_ADAPTERS))
def adapter_id(request: pytest.FixtureRequest) -> str:
    return str(request.param)


def make(adapter_id: str, tmp_path: Path):  # type: ignore[no-untyped-def]
    ctx = AdapterContext(EXAMPLE, load_manifest(EXAMPLE / "asac.yaml"), tmp_path)
    return HARNESS_ADAPTERS[adapter_id](ctx)


def test_has_all_port_methods(adapter_id: str, tmp_path: Path) -> None:
    h = make(adapter_id, tmp_path)
    for m in PORT_METHODS:
        assert callable(getattr(h, m)), m


def test_describe_matches_catalogue(adapter_id: str, tmp_path: Path) -> None:
    if adapter_id == "fake":
        pytest.skip("fake is a test double, not in the catalogue")
    assert make(adapter_id, tmp_path).describe() == HARNESSES[adapter_id]
