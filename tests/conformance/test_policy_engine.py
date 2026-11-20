"""Conformance for the PolicyEngine port, against the OPA adapter (offline)."""

import shutil
from pathlib import Path

import pytest

from asac.adapters.opa_policy import OpaPolicyEngine

pytestmark = pytest.mark.skipif(shutil.which("opa") is None, reason="opa binary not installed")

REGO = """package t.gate

import rego.v1

block contains "too low" if input.score < 5
escalate if input.hours > 24
"""


@pytest.fixture
def engine(tmp_path: Path) -> OpaPolicyEngine:
    (tmp_path / "p.rego").write_text(REGO)
    return OpaPolicyEngine(tmp_path)


def test_allow(engine: OpaPolicyEngine) -> None:
    d = engine.evaluate("p.rego", "t.gate", {"score": 9, "hours": 1})
    assert d.block == [] and not d.escalate


def test_block_and_escalate(engine: OpaPolicyEngine) -> None:
    d = engine.evaluate("p.rego", "t.gate", {"score": 1, "hours": 30})
    assert d.block == ["too low"] and d.escalate


def test_policy_outside_repo_refused(engine: OpaPolicyEngine, tmp_path: Path) -> None:
    with pytest.raises(Exception, match="repo|outside"):
        engine.evaluate("../outside.rego", "t.gate", {})
