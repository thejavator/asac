"""F69: an agent that tries to cheat, run by the real Docker runner. Each attempt must fail.

The agent is a stand-in shell script inside the real agent image, started the way a delegated
step starts it: no network, a read-only root, no privileges, the run's worktree as the only
writable folder. It tries what the spec lists: rewrite a hook, rewrite `asac.yaml`, read a secret,
call an outside host. What is checked is the **disk of the host** afterwards, not what the script
says about itself, and that the script really ran (a test where nothing ran proves nothing).
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from asac.adapters.runner_local import DEFAULT_IMAGE, DockerRunner
from asac.cli import app
from asac.engine import runtime
from tests.conftest import init_git

runner = CliRunner()
EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "real-tools"


def _docker_ready() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        if subprocess.run(["docker", "info"], capture_output=True, timeout=15).returncode != 0:
            return False
        probe = ["docker", "image", "inspect", DEFAULT_IMAGE]
        return subprocess.run(probe, capture_output=True, timeout=15).returncode == 0
    except subprocess.TimeoutExpired:
        return False


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not _docker_ready(), reason=f"docker or the image {DEFAULT_IMAGE} is absent"
    ),
]

DELEGATED = """\
      requirements:
        capability: specification_engineering
        agent: analyst
        mode: delegate
        execution: { runner: docker }
"""


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _tree_digest(root: Path) -> dict[str, str]:
    return {str(p.relative_to(root)): _digest(p) for p in sorted(root.rglob("*")) if p.is_file()}


@pytest.fixture
def arena(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """real-tools under git, its first step delegated to Docker, a secret in a fake $HOME."""
    root = tmp_path / "proj"
    shutil.copytree(EXAMPLE, root)
    shutil.copy(root / "vars" / "claude-code.yaml", root / "asac.vars.yaml")
    text = (root / "asac.yaml").read_text()
    start = text.index("      requirements:")
    end = text.index("        producesEvidence", start)
    (root / "asac.yaml").write_text(text[:start] + DELEGATED + text[end:])
    init_git(root)
    secret = tmp_path / "home" / ".ssh"
    secret.mkdir(parents=True)
    (secret / "id_rsa").write_text("PRIVATE-KEY-MATERIAL")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("ASAC_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("ASAC_FIXED_TIME", "2026-01-01T00:00:00Z")
    monkeypatch.setenv("ASAC_AUTORUN", "0")
    monkeypatch.setenv("ASAC_SANDBOX", "0")
    monkeypatch.setenv("ASAC_RUNNER", "docker")
    return root


def _agent_script(body: str) -> str:
    """The `claude` the container runs: it announces itself, attacks, then reports like a tool."""
    return (
        "echo TOOL-RAN > TOOL-RAN.txt\n"
        + body
        + '\necho \'{"type":"result","is_error":false,"total_cost_usd":0.01,'
        '"usage":{},"result":"done"}\'\n'
    )


class ScriptRunner(DockerRunner):
    """The real Docker runner, with the `claude` command swapped for the hostile script.

    Everything else is the real thing: the container, its mounts, its lockdown, the exec.
    """

    script = ""

    def exec(self, handle: str, argv: list[str], timeout: int):  # type: ignore[no-untyped-def]
        return super().exec(handle, ["sh", "-c", self.script], timeout)


def _attack(root: Path, tmp_path: Path, body: str, run_id: str) -> Path:
    ScriptRunner.script = _agent_script(body)
    real = runtime.runner_from_vars

    def build(root_: Path, values: dict[str, str], wt=None):  # type: ignore[no-untyped-def]
        return ScriptRunner(root_, worktree_for=wt, env={})

    runtime.runner_from_vars = build  # type: ignore[assignment]
    try:
        r = runner.invoke(
            app,
            ["apply", "-p", "feature", "--harness", "claude-code", "--run-id", run_id,
             "-f", str(root / "asac.yaml")],
        )  # fmt: skip
    finally:
        runtime.runner_from_vars = real  # type: ignore[assignment]
    work = tmp_path / "state" / "worktrees" / run_id
    assert (work / "TOOL-RAN.txt").is_file(), f"the container never ran the agent: {r.output}"
    return work


def test_modifying_a_hook_from_the_container_is_refused(arena: Path, tmp_path: Path) -> None:
    hook = arena / ".asac" / "hooks" / "step-scope.sh"
    before = _tree_digest(arena / ".asac")
    work = _attack(arena, tmp_path, (
        f'echo "exit 0" > "{hook}" 2>/dev/null; echo "exit 0" > .asac/hooks/step-scope.sh '
        "2>/dev/null; echo $? > hook-write-status"
    ), "h1")  # fmt: skip
    assert _tree_digest(arena / ".asac") == before, "a hook in the main checkout changed"
    # The worktree is a checkout, so it holds its own copy of the tracked rules, which the agent
    # may rewrite. That copy is not what runs: ASAC runs the main checkout's hooks (R10).
    assert (work / ".asac/hooks/step-scope.sh").read_text().strip() == "exit 0"
    assert (arena / ".asac/hooks/step-scope.sh").read_text().strip() != "exit 0"


def test_modifying_the_manifest_from_the_container_is_refused(arena: Path, tmp_path: Path) -> None:
    manifest = arena / "asac.yaml"
    before = _digest(manifest)
    work = _attack(arena, tmp_path, (
        f'echo "# hacked" >> "{manifest}" 2>/dev/null; echo "# hacked" >> asac.yaml'
    ), "m1")  # fmt: skip
    assert _digest(manifest) == before, "asac.yaml in the main checkout changed"
    # the agent's own copy is not the rules: the worktree has none until the agent makes one,
    # and the integrity check reads the main checkout, which is intact
    log = runner.invoke(app, ["logs", "m1", "-f", str(arena / "asac.yaml")]).output
    assert "integrity.verified" in log and "integrity.violated" not in log
    assert (work / "asac.yaml").read_text().strip().endswith("# hacked")  # only in its own folder


def test_reading_a_secret_of_the_host_from_the_container_is_impossible(
    arena: Path, tmp_path: Path
) -> None:
    key = tmp_path / "home" / ".ssh" / "id_rsa"
    work = _attack(arena, tmp_path, (
        f'cat "{key}" > stolen.txt 2>/dev/null; cat ~/.ssh/id_rsa >> stolen.txt 2>/dev/null; true'
    ), "k1")  # fmt: skip
    stolen = work / "stolen.txt"
    assert not stolen.exists() or "PRIVATE-KEY-MATERIAL" not in stolen.read_text()


def test_calling_an_outside_host_from_the_container_fails(arena: Path, tmp_path: Path) -> None:
    work = _attack(arena, tmp_path, (
        "node -e \"fetch('https://www.wikipedia.org').then(()=>process.exit(0),()=>process.exit(1))\""
        " && echo REACHED > reached.txt || echo BLOCKED > reached.txt"
    ), "n1")  # fmt: skip
    assert (work / "reached.txt").read_text().strip() == "BLOCKED"


def test_the_agent_cannot_make_asac_run_its_command_through_the_worktrees_git(
    arena: Path, tmp_path: Path
) -> None:
    """The container writes a `.git` that points at a repository it made (the F59 finding): the
    commit ASAC makes on the host afterwards must not run what that repository names."""
    marker = tmp_path / "HOST-ESCAPED"
    work = _attack(arena, tmp_path, (
        # A valid SPEC.md, so the step's checks pass and ASAC reaches its commit: an attack that
        # stops the step earlier never exercises the code under test.
        "printf '# Spec\\n## Acceptance criteria\\n- it works\\n' > SPEC.md; "
        "mkdir -p .evil/objects .evil/refs; echo 'ref: refs/heads/main' > .evil/HEAD; "
        f"printf '[core]\\n\\tfsmonitor = \"touch {marker}; true\"\\n' > .evil/config; "
        "echo 'gitdir: .evil' > .git"
    ), "g1")  # fmt: skip
    assert (work / ".evil" / "config").is_file(), "the attack was not written"
    log = runner.invoke(app, ["logs", "g1", "-f", str(arena / "asac.yaml")]).output
    assert "step.committed requirements" in log, "ASAC never reached its commit: test is void"
    assert not marker.exists(), "ASAC ran a command the container planted"


def test_the_rules_are_judged_on_the_main_checkout_whatever_the_agent_wrote(
    arena: Path, tmp_path: Path
) -> None:
    """F69.2: an agent that writes its own `asac.yaml` and hooks in its worktree changes nothing:
    ASAC runs the hooks of the main checkout, on the worktree's files."""
    work = _attack(arena, tmp_path, (
        "mkdir -p .asac/hooks; echo 'exit 0' > .asac/hooks/step-scope.sh; "
        "echo 'asac: {spec: \"0.4\"}' > asac.yaml"
    ), "r1")  # fmt: skip
    log = runner.invoke(app, ["logs", "r1", "-f", str(arena / "asac.yaml")]).output
    # the real step-scope.sh ran, on the worktree: SPEC.md was never written, so it refuses
    assert "hook.failed requirements" in log or "step.blocked requirements" in log
    assert "gate.opened" not in log
    assert (work / ".asac/hooks/step-scope.sh").read_text().strip() == "exit 0"


def test_a_worker_runs_a_delegated_run_in_the_real_container(arena: Path, tmp_path: Path) -> None:
    """F62 with F57: nobody runs `asac apply`. A job is queued, a worker takes it, the real
    container runs the agent, the work lands in the worktree, and the run stops at its gate."""
    ScriptRunner.script = _agent_script(
        "printf '# Spec\\n## Acceptance criteria\\n- it works\\n' > SPEC.md"
    )
    real = runtime.runner_from_vars

    def build(root_: Path, values: dict[str, str], wt=None):  # type: ignore[no-untyped-def]
        return ScriptRunner(root_, worktree_for=wt, env={})

    runtime.runner_from_vars = build  # type: ignore[assignment]
    try:
        manifest = str(arena / "asac.yaml")
        queued = runner.invoke(app, ["apply", "-p", "feature", "--harness", "claude-code",
                                     "--run-id", "wk1", "--enqueue", "-f", manifest])  # fmt: skip
        assert queued.exit_code == 0, queued.output
        assert not (tmp_path / "state" / "worktrees" / "wk1").exists()  # nothing ran yet
        done = runner.invoke(app, ["worker", "--once", "-f", manifest])
    finally:
        runtime.runner_from_vars = real  # type: ignore[assignment]
    assert done.exit_code == 0, done.output
    assert "job 1  wk1  waiting for gate gate_wk1_requirements" in done.output
    work = tmp_path / "state" / "worktrees" / "wk1"
    assert (work / "TOOL-RAN.txt").is_file() and "Acceptance" in (work / "SPEC.md").read_text()
    log = runner.invoke(app, ["logs", "wk1", "-f", manifest]).output
    for event in ("runner.started", "runner.stopped", "step.committed", "gate.opened"):
        assert event in log, event


def test_the_secret_the_agent_prints_is_masked_in_the_audit_and_the_artefact(
    arena: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """F61.2 and F61.3: the key reaches the container by name, the agent prints it, and ASAC
    stores the masked output: neither the audit nor the stored output holds the value."""
    secret = "sk-test-0123456789abcdef"
    monkeypatch.setenv("ASAC_TEST_API_KEY", secret)
    ScriptRunner.script = _agent_script(
        'echo "my key is $ASAC_TEST_API_KEY"; echo "$ASAC_TEST_API_KEY" > leaked.txt'
    )
    real = runtime.runner_from_vars

    def build(root_: Path, values: dict[str, str], wt=None):  # type: ignore[no-untyped-def]
        return ScriptRunner(root_, worktree_for=wt, env={"ASAC_TEST_API_KEY": secret})

    runtime.runner_from_vars = build  # type: ignore[assignment]
    try:
        runner.invoke(app, ["apply", "-p", "feature", "--harness", "claude-code",
                            "--run-id", "s1", "-f", str(arena / "asac.yaml")])  # fmt: skip
    finally:
        runtime.runner_from_vars = real  # type: ignore[assignment]
    work = tmp_path / "state" / "worktrees" / "s1"
    assert (work / "leaked.txt").read_text().strip() == secret  # the agent really had the key
    log = runner.invoke(app, ["logs", "s1", "-f", str(arena / "asac.yaml")]).output
    assert "my key is [redacted]" in log and secret not in log
    for stored in (tmp_path / "state" / "artifacts").rglob("*"):
        if stored.is_file():
            assert secret not in stored.read_text(errors="ignore")
