"""asac doctor: tell a first-time user what is missing before a run fails in the middle."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from asac.cli import app
from asac.doctor import (
    Check,
    check_git_repo,
    check_node,
    check_tool,
    parse_node_version,
    run_checks,
)

runner = CliRunner()


def test_node_versions_are_parsed() -> None:
    assert parse_node_version("v23.11.0") == (23, 11, 0)
    assert parse_node_version("v19.8.1\n") == (19, 8, 1)
    assert parse_node_version("nonsense") is None


def test_an_old_node_is_reported_with_the_version_srt_needs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("asac.doctor._node_version", lambda: "v19.8.1")
    c = check_node()
    assert c.ok is False and "22.12" in c.detail and "19.8.1" in c.detail


def test_a_recent_node_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("asac.doctor._node_version", lambda: "v23.11.0")
    assert check_node().ok is True


def test_a_missing_tool_says_how_to_install_it(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("asac.doctor.shutil.which", lambda name: None)
    c = check_tool("opa", "brew install opa")
    assert c.ok is False and "brew install opa" in c.detail


def test_a_folder_that_is_not_a_git_repository_is_reported(tmp_path: Path) -> None:
    c = check_git_repo(tmp_path)
    assert c.ok is False and "git init" in c.detail


def test_a_repository_with_uncommitted_changes_is_reported(tmp_path: Path) -> None:
    import subprocess

    def git(*a: str) -> None:
        subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", *a], cwd=tmp_path,
                       check=True, capture_output=True)  # fmt: skip

    git("init", "-q", "-b", "main")
    (tmp_path / "a.txt").write_text("x")
    git("add", "-A")
    git("commit", "-q", "-m", "b")
    assert check_git_repo(tmp_path).ok is True
    (tmp_path / "a.txt").write_text("changed")
    c = check_git_repo(tmp_path)
    assert c.ok is False and "uncommitted" in c.detail


def test_the_command_exits_nonzero_when_something_required_is_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "asac.doctor.run_checks",
        lambda root: [Check("opa", True, "ok", True), Check("srt", False, "missing", True)],
    )
    r = runner.invoke(app, ["doctor", "-f", str(tmp_path / "asac.yaml")])
    assert r.exit_code == 1 and "srt" in r.output and "missing" in r.output


def test_an_optional_problem_does_not_fail_the_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "asac.doctor.run_checks",
        lambda root: [Check("opa", True, "ok", True), Check("claude", False, "absent", False)],
    )
    r = runner.invoke(app, ["doctor", "-f", str(tmp_path / "asac.yaml")])
    assert r.exit_code == 0 and "absent" in r.output


def test_run_checks_covers_every_prerequisite(tmp_path: Path) -> None:
    names = {c.name for c in run_checks(tmp_path)}
    assert {"git", "opa", "node", "srt", "claude", "git repository"} <= names


def test_asacs_own_state_folder_does_not_count_as_uncommitted_work(tmp_path: Path) -> None:
    """The default state lives in .asac-state/ inside the project: doctor must not blame the user
    for it after the first run, or it contradicts the next `asac apply`, which works."""
    import subprocess

    def git(*a: str) -> None:
        subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", *a], cwd=tmp_path,
                       check=True, capture_output=True)  # fmt: skip

    git("init", "-q", "-b", "main")
    (tmp_path / "a.txt").write_text("x")
    git("add", "-A")
    git("commit", "-q", "-m", "b")
    (tmp_path / ".asac-state").mkdir()
    (tmp_path / ".asac-state" / "state.db").write_text("db")
    assert check_git_repo(tmp_path).ok is True
    (tmp_path / "a.txt").write_text("changed")  # a real change must still be reported
    assert check_git_repo(tmp_path).ok is False


# --- F58.4 and F60.4: the agent image and the runner network -----------------------------------


def _docker_answers(returncode: int, stdout: str = ""):  # type: ignore[no-untyped-def]
    import subprocess as sp

    def fake(*args: str) -> sp.CompletedProcess[str]:
        return sp.CompletedProcess(["docker", *args], returncode, stdout, "")

    return fake


def test_a_missing_agent_image_comes_with_the_command_that_builds_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from asac.doctor import check_agent_image

    monkeypatch.setattr("asac.doctor._docker", _docker_answers(1))
    c = check_agent_image("asac-agent:0.1.0")
    assert c.ok is False and c.required is False  # only delegated steps need it
    assert "docker build -t asac-agent:0.1.0" in c.detail
    assert "docker/agent" in c.detail and "ASAC_VERSION=" in c.detail


def test_a_present_agent_image_is_reported_by_name(monkeypatch: pytest.MonkeyPatch) -> None:
    from asac.doctor import check_agent_image

    monkeypatch.setattr("asac.doctor._docker", _docker_answers(0))
    c = check_agent_image("asac-agent:0.1.0")
    assert c.ok is True and c.detail == "asac-agent:0.1.0"


def test_a_docker_that_does_not_answer_is_not_a_crash(monkeypatch: pytest.MonkeyPatch) -> None:
    from asac.doctor import check_agent_image, check_runner_network

    monkeypatch.setattr("asac.doctor._docker", lambda *a: None)
    assert (
        check_agent_image("x").ok is False
        and "docker does not answer" in check_agent_image("x").detail
    )
    assert check_runner_network("n").ok is False


def test_a_named_network_that_does_not_exist_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    from asac.doctor import check_runner_network

    monkeypatch.setattr("asac.doctor._docker", _docker_answers(1))
    c = check_runner_network("asac-egress")
    assert c.ok is False and c.required is False
    assert "asac-egress" in c.detail and "docker network create asac-egress" in c.detail
    monkeypatch.setattr("asac.doctor._docker", _docker_answers(0))
    assert check_runner_network("asac-egress").ok is True


def test_the_network_is_only_checked_when_the_operator_names_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("asac.doctor._docker", _docker_answers(0))
    assert "runner network" not in {c.name for c in run_checks(tmp_path)}  # default: none
    (tmp_path / "asac.vars.yaml").write_text("runner_network: asac-egress\n")
    assert "runner network" in {c.name for c in run_checks(tmp_path)}


def test_the_image_checked_is_the_one_the_vars_file_names(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[tuple[str, ...]] = []

    def spy(*args: str):  # type: ignore[no-untyped-def]
        seen.append(args)
        return _docker_answers(0)(*args)

    monkeypatch.setattr("asac.doctor._docker", spy)
    (tmp_path / "asac.vars.yaml").write_text("runner_image: my-registry/agent:7\n")
    run_checks(tmp_path)
    assert ("image", "inspect", "my-registry/agent:7") in seen
