"""Golden output per validator error code. Regenerate with ASAC_UPDATE_GOLDEN=1."""

import os
from collections.abc import Callable
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from asac.cli import app

runner = CliRunner()
GOLDEN = Path(__file__).parent / "golden"
Mut = Callable[[dict], None]
STEPS = lambda d: d["pipelines"]["feature"]["steps"]  # noqa: E731

CASES: dict[str, Mut] = {
    "ASAC000_v05_key": lambda d: d.update(routing={}),
    "ASAC000_bad_spec": lambda d: d["asac"].update(spec="0.5"),
    "ASAC001": lambda d: STEPS(d)["release"].update(capability="nope"),
    "ASAC002": lambda d: STEPS(d)["release"].update(agent="nope"),
    "ASAC003": lambda d: d["agents"]["ba"].update(skill="nope"),
    "ASAC004": lambda d: d["agents"]["ba"].update(provider="nope"),
    "ASAC005": lambda d: d["skills"]["spec"].update(fulfils="nope"),
    "ASAC006": lambda d: STEPS(d)["release"].update(agent="ba"),
    "ASAC007": lambda d: STEPS(d)["release"].update(dependsOn=["nope"]),
    "ASAC008": lambda d: STEPS(d)["requirements"].update(dependsOn=["release"]),
    "ASAC009": lambda d: STEPS(d)["development"].update(dependsOn=[]),
    "ASAC010": lambda d: STEPS(d)["release"].update(producesEvidence=["nope"]),
    "ASAC011": lambda d: d["hooks"]["definitions"]["secret-scan"].update(run="../evil.sh"),
    "ASAC012": lambda d: d["hooks"].update(pre_tool=["nope"]),
    "ASAC014": lambda d: d["agents"]["ba"].update(harness="var.nope"),
    "ASAC015": lambda d: d["agents"]["ba"].update(harness="nope"),
    "ASAC018": lambda d: d["hooks"]["definitions"].update(x={"ref": "not-a-ref"}),
    "ASAC019": lambda d: d["hooks"]["definitions"].update(x={"ref": "registry.example.dev/h@1"}),
    "ASAC024": lambda d: d["providers"]["jira"].update(mcp={"command": "x", "url": "https://h"}),
    "ASAC025": lambda d: d["providers"]["jira"].update(mcp={"command": "x", "env": {"T": "abc"}}),
    "ASAC020": lambda d: STEPS(d)["release"]["gate"].pop("role"),
}


@pytest.mark.parametrize("case", sorted(CASES))
def test_golden(case: str, sandbox_project: Path) -> None:
    f = sandbox_project / "asac.yaml"
    data = yaml.safe_load(f.read_text())
    CASES[case](data)
    f.write_text(yaml.safe_dump(data))
    r = runner.invoke(app, ["validate", "-f", str(f)])
    out = (
        "\n".join(ln for ln in r.output.splitlines() if "ASAC017" not in ln)
        + f"\nexit={r.exit_code}\n"
    )
    gold = GOLDEN / f"{case}.txt"
    if os.environ.get("ASAC_UPDATE_GOLDEN"):
        GOLDEN.mkdir(exist_ok=True)
        gold.write_text(out)
    assert out == gold.read_text()
    assert r.exit_code == 1
    assert case.split("_")[0] in out


def test_v05_message(sandbox_project: Path) -> None:
    f = sandbox_project / "asac.yaml"
    data = yaml.safe_load(f.read_text())
    data["routing"] = {}
    f.write_text(yaml.safe_dump(data))
    assert "not in spec v0.4" in runner.invoke(app, ["validate", "-f", str(f)]).output


def test_init_detects_stack_and_template(tmp_path: Path) -> None:
    (tmp_path / "pom.xml").write_text("<project/>")
    assert runner.invoke(app, ["init", str(tmp_path), "--template", "feature"]).exit_code == 0
    assert "registry.example.dev/java/" in (tmp_path / "asac.yaml").read_text()
    assert runner.invoke(app, ["validate", "-f", str(tmp_path / "asac.yaml")]).exit_code == 0
    assert runner.invoke(app, ["init", str(tmp_path), "--template", "x", "--force"]).exit_code == 1


def test_spec_level_warnings(sandbox_project: Path) -> None:
    f = sandbox_project / "asac.yaml"
    assert "ASAC026" not in runner.invoke(app, ["validate", "-f", str(f)]).output
    data = yaml.safe_load(f.read_text())
    data["hooks"]["post_step"], data["hooks"]["pre_tool"] = [], []
    for st in STEPS(data).values():
        st["policies"] = []
    f.write_text(yaml.safe_dump(data))
    r = runner.invoke(app, ["validate", "-f", str(f)])
    assert r.exit_code == 0 and "ASAC026" in r.output and "specLevel 3" in r.output
    data = yaml.safe_load(f.read_text())
    for st in STEPS(data).values():
        st["producesEvidence"], st["requiresEvidence"] = [], []
    data["pipelines"]["feature"]["specLevel"] = 2
    f.write_text(yaml.safe_dump(data))
    assert "specLevel 2" in runner.invoke(app, ["validate", "-f", str(f)]).output
