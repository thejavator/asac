import shutil
from pathlib import Path

import yaml
from typer.testing import CliRunner

from asac.cli import app
from asac.loader.load import load_manifest, load_vars
from asac.validate import Severity, validate

runner = CliRunner()


def _codes(project: Path, mutate) -> set[str]:
    data = yaml.safe_load((project / "asac.yaml").read_text())
    mutate(data)
    (project / "asac.yaml").write_text(yaml.safe_dump(data))
    return {
        i.code
        for i in validate(load_manifest(project / "asac.yaml"), project)
        if i.severity is Severity.ERROR
    }


def test_example_has_no_errors(sandbox_project: Path) -> None:
    vf = load_vars(sandbox_project / "asac.vars.yaml.example")
    issues = validate(load_manifest(sandbox_project / "asac.yaml"), sandbox_project, vf)
    assert [i for i in issues if i.severity is Severity.ERROR] == []


def test_unknown_agent(sandbox_project: Path) -> None:
    c = _codes(
        sandbox_project, lambda d: d["pipelines"]["feature"]["steps"]["release"].update(agent="x")
    )
    assert "ASAC002" in c


def test_fulfils_mismatch(sandbox_project: Path) -> None:
    c = _codes(
        sandbox_project, lambda d: d["pipelines"]["feature"]["steps"]["release"].update(agent="ba")
    )
    assert "ASAC006" in c


def test_missing_upstream_evidence(sandbox_project: Path) -> None:
    c = _codes(
        sandbox_project,
        lambda d: d["pipelines"]["feature"]["steps"]["development"].update(dependsOn=[]),
    )
    assert "ASAC009" in c


def test_cycle(sandbox_project: Path) -> None:
    c = _codes(
        sandbox_project,
        lambda d: d["pipelines"]["feature"]["steps"]["requirements"].update(dependsOn=["release"]),
    )
    assert "ASAC008" in c


def test_missing_path_and_outside_repo(sandbox_project: Path) -> None:
    c = _codes(
        sandbox_project, lambda d: d["hooks"]["definitions"]["secret-scan"].update(run="../evil.sh")
    )
    assert "ASAC011" in c


def test_delegate_needs_headless(sandbox_project: Path) -> None:
    vf = (
        (sandbox_project / "asac.vars.yaml.example")
        .read_text()
        .replace("dev_harness: claude-code", "dev_harness: copilot")
    )
    (sandbox_project / "asac.vars.yaml").write_text(vf)
    issues = validate(
        load_manifest(sandbox_project / "asac.yaml"),
        sandbox_project,
        load_vars(sandbox_project / "asac.vars.yaml"),
    )
    assert "ASAC013" in {i.code for i in issues}


def test_cli_validate_ok_and_fail(sandbox_project: Path) -> None:
    f = sandbox_project / "asac.yaml"
    assert runner.invoke(app, ["validate", "-f", str(f)]).exit_code == 0
    data = yaml.safe_load(f.read_text())
    data["pipelines"]["feature"]["steps"]["release"]["agent"] = "nope"
    f.write_text(yaml.safe_dump(data))
    r = runner.invoke(app, ["validate", "-f", str(f)])
    assert r.exit_code == 1 and "ASAC002" in r.output


def test_vars_diff_ignores_reserved(sandbox_project: Path) -> None:
    shutil.copy(sandbox_project / "asac.vars.yaml.example", sandbox_project / "asac.vars.yaml")
    r = runner.invoke(app, ["vars", "diff", "-f", str(sandbox_project / "asac.yaml")])
    assert r.exit_code == 0 and "state_backend" not in r.output and "data_residency" not in r.output


def test_vars_check_missing(sandbox_project: Path) -> None:
    (sandbox_project / "asac.vars.yaml").write_text("jira_url: x\n")
    r = runner.invoke(app, ["vars", "check", "-f", str(sandbox_project / "asac.yaml")])
    assert r.exit_code == 1 and "missing: gitlab_url" in r.output


def test_init_then_validate(tmp_path: Path) -> None:
    assert runner.invoke(app, ["init", str(tmp_path / "p")]).exit_code == 0
    assert runner.invoke(app, ["validate", "-f", str(tmp_path / "p" / "asac.yaml")]).exit_code == 0
    assert runner.invoke(app, ["init", str(tmp_path / "p")]).exit_code == 1


# --- F63: a delegate step needs a runner, caught when the manifest is written -----------------


def _issues(project: Path, mutate):  # type: ignore[no-untyped-def]
    data = yaml.safe_load((project / "asac.yaml").read_text())
    mutate(data)
    (project / "asac.yaml").write_text(yaml.safe_dump(data))
    return [i for i in validate(load_manifest(project / "asac.yaml"), project)]


def _step(data: dict, name: str) -> dict:  # type: ignore[type-arg]
    step: dict = data["pipelines"]["feature"]["steps"][name]  # type: ignore[type-arg]
    return step


def test_a_delegate_step_without_a_runner_is_an_error_with_its_path(sandbox_project: Path) -> None:
    issues = _issues(sandbox_project, lambda d: _step(d, "development").pop("execution"))
    hits = [i for i in issues if i.code == "ASAC028"]
    assert [(i.severity, i.path) for i in hits] == [
        (Severity.ERROR, "pipelines.feature.steps.development.execution")
    ]


def test_a_delegate_step_with_an_empty_execution_block_is_also_an_error(
    sandbox_project: Path,
) -> None:
    issues = _issues(sandbox_project, lambda d: _step(d, "development").update(execution={}))
    assert any(i.code == "ASAC028" for i in issues)  # a fallback alone does not name a runner
    issues = _issues(
        sandbox_project,
        lambda d: _step(d, "development").update(execution={"fallback": "assist"}),
    )
    assert any(i.code == "ASAC028" for i in issues)


def test_a_delegate_step_with_a_runner_is_valid(sandbox_project: Path) -> None:
    issues = _issues(sandbox_project, lambda d: None)
    assert [i for i in issues if i.code == "ASAC028"] == []
    assert [i for i in issues if i.severity is Severity.ERROR] == []


def test_the_fallback_stays_accepted_next_to_a_runner(sandbox_project: Path) -> None:
    issues = _issues(
        sandbox_project,
        lambda d: _step(d, "development").update(
            execution={"runner": "docker", "fallback": "assist"}
        ),
    )
    assert [i for i in issues if i.severity is Severity.ERROR] == []


def test_an_assist_step_needs_no_runner(sandbox_project: Path) -> None:
    def make_assist(d: dict) -> None:  # type: ignore[type-arg]
        step = _step(d, "development")
        step["mode"] = "assist"
        step.pop("execution")

    assert [i for i in _issues(sandbox_project, make_assist) if i.code == "ASAC028"] == []


def test_every_delegate_step_is_reported_not_only_the_first(sandbox_project: Path) -> None:
    def strip(d: dict) -> None:  # type: ignore[type-arg]
        for name in ("development", "release"):
            _step(d, name).pop("execution")

    paths = sorted(i.path for i in _issues(sandbox_project, strip) if i.code == "ASAC028")
    assert paths == [
        "pipelines.feature.steps.development.execution",
        "pipelines.feature.steps.release.execution",
    ]
