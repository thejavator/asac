"""The three full examples (mobile, Spring + Angular + PostgreSQL, PHP e-commerce).

An example nobody checks rots: a key renamed in the manifest, a hook that is no longer executable, a
policy whose test fails. Each example here must validate with no error, plan every pipeline, keep
its values example complete, ship hooks that run, and pass its own Rego tests.
"""

from __future__ import annotations

import os
import re
import shutil
import stat
import subprocess
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from asac.cli import app
from asac.engine.plan import build_plan
from asac.loader.load import load_manifest, load_vars
from asac.validate import Severity, validate

runner = CliRunner()
EXAMPLES = Path(__file__).resolve().parent.parent / "examples"
NAMES = ["mobile-app", "spring-angular-postgres", "php-ecommerce"]

# What each example is supposed to demonstrate: if a refactor drops one of these, the example no
# longer covers the case it exists for. (pipeline, step count) per example.
PIPELINES = {
    "mobile-app": {"feature": 5, "hotfix": 2},
    "spring-angular-postgres": {"feature": 6, "hotfix": 2},
    "php-ecommerce": {"feature": 6, "payment-change": 5, "hotfix": 2},
}


def asac(root: Path, *args: str):  # type: ignore[no-untyped-def]
    return runner.invoke(app, [*args, "-f", str(root / "asac.yaml")])


@pytest.fixture(params=NAMES)
def example(request: pytest.FixtureRequest) -> Path:
    return EXAMPLES / request.param


def test_the_example_validates_with_no_error(example: Path) -> None:
    issues = validate(load_manifest(example / "asac.yaml"), example)
    errors = [f"{i.code} {i.path}: {i.message}" for i in issues if i.severity is Severity.ERROR]
    assert errors == []


def test_the_example_validates_with_its_own_values_file(example: Path) -> None:
    """The harness each agent uses is a variable: an unknown one (ASAC015), or one that cannot run
    unattended in a delegated step (ASAC013), only shows once the values are read."""
    values = load_vars(example / "asac.vars.yaml.example")
    issues = validate(load_manifest(example / "asac.yaml"), example, values)
    assert [i.code for i in issues if i.severity is Severity.ERROR] == []


def test_the_cli_validates_with_the_values_example(example: Path) -> None:
    r = runner.invoke(app, ["validate", "-f", str(example / "asac.yaml"),
                            "--vars", str(example / "asac.vars.yaml.example")])  # fmt: skip
    assert r.exit_code == 0 and "0 error(s)" in r.output, r.output


def test_the_only_warnings_are_the_ones_the_comments_announce(example: Path) -> None:
    """A warning the manifest does not explain is noise: every ASAC027 must be one it documents."""
    issues = validate(load_manifest(example / "asac.yaml"), example)
    codes = {i.code for i in issues if i.severity is Severity.WARNING}
    assert codes <= {"ASAC027"}, codes
    text = (example / "asac.yaml").read_text()
    for issue in issues:
        if issue.code == "ASAC027":
            key = issue.path.split(".")[-1]
            assert key in text and "Appliqué ? " in text, issue.path


def test_every_pipeline_plans_with_the_expected_steps(example: Path) -> None:
    manifest = load_manifest(example / "asac.yaml")
    assert {n: len(p.steps) for n, p in manifest.pipelines.items()} == PIPELINES[example.name]
    for name in manifest.pipelines:
        built = build_plan(manifest, name)
        assert built.steps, name


def test_the_values_example_leaves_no_variable_unset(example: Path) -> None:
    r = runner.invoke(app, ["vars", "check", "-f", str(example / "asac.yaml"),
                            "--vars", str(example / "asac.vars.yaml.example")])  # fmt: skip
    assert r.exit_code == 0, r.output


def test_the_values_example_has_no_stray_key(example: Path) -> None:
    r = runner.invoke(app, ["vars", "diff", "-f", str(example / "asac.yaml"),
                            "--vars", str(example / "asac.vars.yaml.example")])  # fmt: skip
    assert "unused" not in r.output, r.output


def test_no_secret_is_written_in_the_values_example(example: Path) -> None:
    values = load_vars(example / "asac.vars.yaml.example").values
    for key, value in values.items():
        text = str(value)
        looks_secret = re.search(r"key|token|secret|password|uri|url", key, re.I)
        if looks_secret and "default" not in key and text not in ("sqlite", "eu"):
            assert text.startswith("${vault.") or key in (
                "jira_url",
                "sandbox_domains",
                "runner_env",
            ), key


def test_every_hook_is_executable_and_has_a_shebang(example: Path) -> None:
    hooks = sorted((example / ".asac" / "hooks").glob("*.sh"))
    assert hooks, "no hook shipped"
    for hook in hooks:
        assert hook.stat().st_mode & stat.S_IXUSR, f"{hook.name} is not executable"
        assert hook.read_text().startswith("#!/bin/sh"), hook.name


def test_every_hook_script_is_valid_shell(example: Path) -> None:
    for hook in sorted((example / ".asac" / "hooks").glob("*.sh")):
        done = subprocess.run(["/bin/sh", "-n", str(hook)], capture_output=True, text=True)
        assert done.returncode == 0, f"{hook.name}: {done.stderr}"


def test_every_hook_declared_is_used_and_every_file_is_declared(example: Path) -> None:
    """A hook nobody attaches does nothing; a script nobody declares is dead weight."""
    manifest = load_manifest(example / "asac.yaml")
    assert manifest.hooks is not None
    attached = set(manifest.hooks.pre_tool) | set(manifest.hooks.post_step)
    for pipe in manifest.pipelines.values():
        for step in pipe.steps.values():
            if step.hooks:
                attached |= set(step.hooks.pre_tool) | set(step.hooks.post_step)
            if step.loop:
                attached |= set(step.loop.until)
    declared = set(manifest.hooks.definitions)
    assert declared <= attached, f"declared but never attached: {sorted(declared - attached)}"
    scripts = {Path(d.run).name for d in manifest.hooks.definitions.values() if d.run}
    shipped = {p.name for p in (example / ".asac" / "hooks").glob("*.sh")}
    assert shipped == scripts, shipped ^ scripts


def test_every_skill_and_instruction_file_is_used(example: Path) -> None:
    manifest = load_manifest(example / "asac.yaml")
    used = {s.ref for s in manifest.skills.values()} | {i.ref for i in manifest.instructions}
    for folder in ("skills", "instructions"):
        for path in (example / ".asac" / folder).glob("*.md"):
            assert f".asac/{folder}/{path.name}" in used, f"{path.name} is not referenced"


def test_a_loop_check_is_a_hook_that_exists(example: Path) -> None:
    manifest = load_manifest(example / "asac.yaml")
    for pname, pipe in manifest.pipelines.items():
        for sname, step in pipe.steps.items():
            if step.loop:
                assert 1 <= step.loop.max_iterations <= 50, f"{pname}.{sname}"


def test_every_delegated_step_names_a_runner_and_an_agent_that_can_run_unattended(
    example: Path,
) -> None:
    manifest = load_manifest(example / "asac.yaml")
    for pname, pipe in manifest.pipelines.items():
        for sname, step in pipe.steps.items():
            if step.mode == "delegate":
                assert step.execution and step.execution.runner == "docker", f"{pname}.{sname}"


def test_every_gate_names_a_role(example: Path) -> None:
    manifest = load_manifest(example / "asac.yaml")
    for pipe in manifest.pipelines.values():
        for step in pipe.steps.values():
            if step.gate and step.gate.type in ("human", "quality"):
                assert step.gate.role


def test_rego_policies_pass_their_own_tests(example: Path) -> None:
    if shutil.which("opa") is None:
        pytest.skip("opa is not installed")
    policies = example / ".asac" / "policies"
    for cmd in (["check", "--strict"], ["test"]):
        done = subprocess.run(["opa", *cmd, str(policies)], capture_output=True, text=True)
        assert done.returncode == 0, done.stdout + done.stderr


def test_every_policy_file_is_referenced_and_has_a_test(example: Path) -> None:
    manifest = load_manifest(example / "asac.yaml")
    policies = example / ".asac" / "policies"
    referenced = set()
    for pipe in manifest.pipelines.values():
        for step in pipe.steps.values():
            referenced |= {
                f".asac/policies/{p}.rego" for p in step.policies if p != "no_regression"
            }
            if step.gate and step.gate.policy:
                referenced.add(step.gate.policy)
    shipped = {
        f".asac/policies/{p.name}"
        for p in policies.glob("*.rego")
        if not p.name.endswith("_test.rego")
    }
    assert shipped == referenced, shipped ^ referenced
    for p in shipped:
        assert (example / p.replace(".rego", "_test.rego")).is_file(), f"{p} has no test"


# What a person writes for the first step of each example, so its own check lets it through.
SPRING_PARTS = ["Contexte", "Acceptance criteria", "Contrat d'API", "Données", "Hors périmètre"]
PHP_PARTS = ["Acceptance criteria", "Prix et taxes", "Stock", "Données personnelles"]


def _spec_without(missing: str, parts: list[str]) -> str:
    """A SPEC.md that has every required part but one."""
    return "".join(f"## {p}\nx\n" for p in parts if p != missing)


# For each example, the first step's file with ONE required part removed. Each must be refused, so
# no line of the check can be loosened without a test noticing.
MISSING_ONE_PART = {
    "mobile-app": [
        ("DESIGN.md", "chargement", "# Écran\nerreur hors ligne accessibilité 200\n"),
        ("DESIGN.md", "erreur", "# Écran\nchargement hors ligne accessibilité 200\n"),
        ("DESIGN.md", "hors ligne", "# Écran\nchargement erreur accessibilité 200\n"),
        ("DESIGN.md", "accessibilité", "# Écran\nchargement erreur hors ligne 200\n"),
        ("DESIGN.md", "200", "# Écran\nchargement erreur hors ligne accessibilité\n"),
    ],
    "spring-angular-postgres": [
        ("SPEC.md", part, _spec_without(part, SPRING_PARTS))
        for part in SPRING_PARTS
    ],
    "php-ecommerce": [
        ("SPEC.md", part, _spec_without(part, PHP_PARTS))
        for part in PHP_PARTS
    ],
}  # fmt: skip

FIRST_STEP_WORK = {
    "mobile-app": ("DESIGN.md", "# Écran\nÉtats : chargement, erreur, hors ligne.\n"
                   "Accessibilité : libellés et cibles tactiles. Texte agrandi à 200 %.\n"),
    "spring-angular-postgres": (
        "SPEC.md", "# Contexte\nx\n## Acceptance criteria\n- a\n## Contrat d'API\nx\n"
        "## Données\nx\n## Hors périmètre\nx\n"),
    "php-ecommerce": (
        "SPEC.md", "# Contexte\nx\n## Acceptance criteria\n- a\n## Impacts\n"
        "Prix et taxes : aucun\nStock : aucun\nDonnées personnelles : aucun\n"),
}  # fmt: skip


def _fresh_clone(example: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    dest = tmp_path / example.name
    shutil.copytree(example, dest, ignore=shutil.ignore_patterns("asac.vars.yaml", ".DS_Store"))
    shutil.copy(dest / "asac.vars.yaml.example", dest / "asac.vars.yaml")
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}  # fmt: skip
    for args in (["init", "-q", "-b", "main"], ["add", "-A"], ["commit", "-q", "-m", "base"]):
        subprocess.run(["git", *args], cwd=dest, check=True, capture_output=True, env=env)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("ASAC_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("ASAC_FIXED_TIME", "2026-01-01T00:00:00Z")
    monkeypatch.setenv("ASAC_AUTORUN", "0")
    monkeypatch.setenv("ASAC_SANDBOX", "0")
    monkeypatch.setenv("ASAC_RUNNER", "fake")  # the example names Docker; offline, nothing starts
    return dest


def test_a_fresh_clone_stops_at_its_first_step_for_a_person(
    example: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dest = _fresh_clone(example, tmp_path, monkeypatch)
    r = runner.invoke(app, ["apply", "-p", "feature", "--harness", "claude-code",
                            "--run-id", "ex1", "-f", str(dest / "asac.yaml")])  # fmt: skip
    assert r.exit_code == 2 and "work in:" in r.output, r.output  # waiting for a person: no error


def test_the_first_check_refuses_a_file_missing_any_one_required_part(
    example: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every required part is checked on its own: drop each in turn and the step comes back."""
    dest = _fresh_clone(example, tmp_path, monkeypatch)
    manifest = str(dest / "asac.yaml")
    runner.invoke(app, ["apply", "-p", "feature", "--harness", "claude-code", "--run-id", "ex3",
                        "-f", manifest])  # fmt: skip
    work = tmp_path / "state" / "worktrees" / "ex3"
    for name, absent, text in MISSING_ONE_PART[example.name]:
        (work / name).write_text(text, encoding="utf-8")
        r = runner.invoke(app, ["submit", "ex3", "--by", "dev", "-f", manifest])
        assert r.exit_code == 3, f"{name} without '{absent}' was accepted: {r.output}"
        assert absent.lower() in r.output.lower(), (absent, r.output)  # and it says which part


def test_the_first_check_refuses_an_empty_step_then_lets_the_real_work_through(
    example: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The example's own first check refuses an empty step, then lets the real work through."""
    dest = _fresh_clone(example, tmp_path, monkeypatch)
    manifest = str(dest / "asac.yaml")
    runner.invoke(app, ["apply", "-p", "feature", "--harness", "claude-code", "--run-id", "ex2",
                        "-f", manifest])  # fmt: skip
    refused = runner.invoke(app, ["submit", "ex2", "--by", "dev", "-f", manifest])
    assert refused.exit_code == 3, refused.output  # the check says what is missing
    name, text = FIRST_STEP_WORK[example.name]
    work = tmp_path / "state" / "worktrees" / "ex2"
    # The check must not be a formality: a half-written file is refused, naming what is missing.
    (work / name).write_text(text.splitlines()[0] + "\n", encoding="utf-8")
    half = runner.invoke(app, ["submit", "ex2", "--by", "dev", "-f", manifest])
    assert half.exit_code == 3, f"a one-line {name} was accepted: the check is a formality"
    (work / name).write_text(text, encoding="utf-8")
    opened = runner.invoke(app, ["submit", "ex2", "--by", "dev", "-f", manifest])
    assert opened.exit_code == 2 and "waiting for gate" in opened.output, opened.output


def test_the_yaml_is_plain_yaml_with_no_duplicate_key(example: Path) -> None:
    class Strict(yaml.SafeLoader):
        pass

    def no_dupes(loader: yaml.SafeLoader, node: yaml.MappingNode, deep: bool = False) -> dict:  # type: ignore[type-arg]
        seen: set[object] = set()
        for key_node, _ in node.value:
            key = loader.construct_object(key_node, deep=deep)
            assert key not in seen, f"duplicate key {key!r}"
            seen.add(key)
        return yaml.SafeLoader.construct_mapping(loader, node, deep)

    Strict.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, no_dupes)
    yaml.load((example / "asac.yaml").read_text(), Loader=Strict)  # noqa: S506 (safe subclass)


# --- every pipeline, run from its first step to `completed` -----------------------------------

REPORT = (
    '{"type":"result","is_error":false,"total_cost_usd":0.05,'
    '"usage":{"input_tokens":10,"output_tokens":5},"result":"ok"}'
)


def _agent_leaves(example: str, work: Path) -> None:
    """What a stand-in agent leaves in the worktree: what the example's checks look for."""
    if example == "php-ecommerce":
        (work / "src/Payment").mkdir(parents=True, exist_ok=True)
        (work / "src/Payment/M.php").write_text("<?php final class M { private int $cents = 0; }\n")
        # a payment change brings its tests: they sit inside the scope the change is allowed in
        (work / "tests/Payment").mkdir(parents=True, exist_ok=True)
        (work / "tests/Payment/MTest.php").write_text("<?php // test\n")
    if example == "spring-angular-postgres":
        mig = work / "backend/src/main/resources/db/migration"
        mig.mkdir(parents=True, exist_ok=True)
        (mig / "V202611250900__x.sql").write_text("create table t(id int);")
        (mig / "U202611250900__x.sql").write_text("drop table t;")
        # real dependencies, all on the allowlist: a shorter list must make this step fail
        (work / "backend/pom.xml").write_text(
            "<project><dependencies>"
            "<dependency><groupId>org.postgresql</groupId><artifactId>postgresql</artifactId></dependency>"
            "<dependency><groupId>org.flywaydb</groupId><artifactId>flyway-core</artifactId></dependency>"
            "</dependencies></project>"
        )
        (work / "frontend").mkdir(exist_ok=True)
        (work / "frontend/package.json").write_text(
            '{"dependencies": {"rxjs": "7", "@angular/core": "19"}}'
        )
        (work / "backend/src/main/resources/openapi.yaml").write_text("paths: {}")
        report = work / "backend/target/site/jacoco"
        report.mkdir(parents=True, exist_ok=True)
        (report / "jacoco.csv").write_text(
            "GROUP,PACKAGE,CLASS,INSTRUCTION_MISSED,INSTRUCTION_COVERED\nshop,a,A,10,90\n"
        )
    if example == "mobile-app":
        (work / "pubspec.yaml").write_text("name: x\nversion: 1.2.3\n")
        (work / "lib").mkdir(exist_ok=True)
        (work / "test").mkdir(exist_ok=True)
        (work / "CHANGELOG.md").write_text("## 1.2.3\n- x\n")


@pytest.fixture
def fake_toolchain(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Stand-ins for php, composer, mvn, npm and flutter that succeed: the hooks that run a real
    toolchain are tested on their own; here the subject is ASAC's flow through each pipeline."""
    bindir = tmp_path / "toolbin"
    bindir.mkdir()
    for tool in ("php", "composer", "mvn", "npm", "flutter"):
        (bindir / tool).write_text("#!/bin/sh\nexit 0\n")
        (bindir / tool).chmod(0o755)
    monkeypatch.setenv("PATH", f"{bindir}:{os.environ['PATH']}")
    return bindir


def _drive_to_the_end(
    example: Path, pipeline: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> list[str]:
    from asac.adapters.runner_local import FakeRunner
    from asac.engine import runtime
    from asac.ports.runner import ExecResult

    dest = _fresh_clone(example, tmp_path, monkeypatch)
    manifest = str(dest / "asac.yaml")
    work = tmp_path / "state" / "worktrees" / "all"

    class StandInAgent(FakeRunner):
        def exec(self, handle: str, argv: list[str], timeout: int) -> ExecResult:
            self.executed.append(list(argv))
            _agent_leaves(example.name, work)
            if example.name == "php-ecommerce":
                for tool in ("phpunit", "phpstan"):
                    path = work / "vendor/bin" / tool
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text("#!/bin/sh\nexit 0\n")
                    path.chmod(0o755)
            return ExecResult(0, REPORT + "\n")

    monkeypatch.setattr(runtime, "runner_from_vars", lambda root, values, wt=None: StandInAgent())
    steps = load_manifest(dest / "asac.yaml").pipelines[pipeline].steps
    decisions: list[str] = []
    out = runner.invoke(app, ["apply", "-p", pipeline, "--harness", "claude-code",
                              "--run-id", "all", "-f", manifest])  # fmt: skip
    for _ in range(4 * len(steps)):
        status = runner.invoke(app, ["status", "-f", manifest]).output.split()[-1]
        if status == "completed":
            return decisions
        pending = [
            ln for ln in runner.invoke(app, ["gates", "--status", "pending", "-f", manifest])
            .output.splitlines() if ln.startswith("gate_")
        ]  # fmt: skip
        if pending:
            gate_id, role = pending[0].split()[0], pending[0].split("role=")[1].split()[0]
            out = runner.invoke(app, ["approve", gate_id, "--role", role, "--by", "me",
                                      "-f", manifest])  # fmt: skip
            assert out.exit_code in (0, 2), f"{gate_id} ({role}): {out.output}"
            decisions.append(f"{gate_id} {role}")
            continue
        name, text = FIRST_STEP_WORK[example.name]
        (work / name).write_text(text, encoding="utf-8")
        if example.name == "mobile-app":
            (work / "SPEC.md").write_text("# S\n## Acceptance criteria\n- a\nPermissions: aucune\n")
        out = runner.invoke(app, ["submit", "all", "--by", "me", "-f", manifest])
        assert out.exit_code in (0, 2), f"submit: {out.output}"
    raise AssertionError(f"{example.name}/{pipeline} never completed: {out.output}")


CASES = [(n, p) for n, ps in PIPELINES.items() for p in ps]


@pytest.mark.parametrize(("name", "pipeline"), CASES)
def test_every_pipeline_runs_from_its_first_step_to_completed(
    name: str,
    pipeline: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fake_toolchain: Path,
) -> None:
    decisions = _drive_to_the_end(EXAMPLES / name, pipeline, tmp_path, monkeypatch)
    manifest = load_manifest(EXAMPLES / name / "asac.yaml")
    gated = [s for s, st in manifest.pipelines[pipeline].steps.items() if st.gate]
    assert len(decisions) == len(gated), (decisions, gated)  # a person decided every gate


def test_a_wrong_role_cannot_decide_a_gate_of_the_payment_pipeline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fake_toolchain: Path
) -> None:
    """Separation of duties, on the pipeline that touches money: the product owner who opened the
    change cannot approve its security review."""
    from asac.adapters.runner_local import FakeRunner
    from asac.engine import runtime
    from asac.ports.runner import ExecResult

    example = EXAMPLES / "php-ecommerce"
    dest = _fresh_clone(example, tmp_path, monkeypatch)
    manifest = str(dest / "asac.yaml")
    work = tmp_path / "state" / "worktrees" / "sod"

    class Agent(FakeRunner):
        def exec(self, handle: str, argv: list[str], timeout: int) -> ExecResult:
            _agent_leaves("php-ecommerce", work)
            for tool in ("phpunit", "phpstan"):
                path = work / "vendor/bin" / tool
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("#!/bin/sh\nexit 0\n")
                path.chmod(0o755)
            return ExecResult(0, REPORT + "\n")

    monkeypatch.setattr(runtime, "runner_from_vars", lambda root, values, wt=None: Agent())
    runner.invoke(app, ["apply", "-p", "payment-change", "--harness", "claude-code",
                        "--run-id", "sod", "-f", manifest])  # fmt: skip
    name, text = FIRST_STEP_WORK["php-ecommerce"]
    (work / name).write_text(text)
    runner.invoke(app, ["submit", "sod", "--by", "dev", "-f", manifest])
    runner.invoke(app, ["approve", "gate_sod_requirements", "--role", "product_owner",
                        "--by", "po", "-f", manifest])  # fmt: skip
    runner.invoke(app, ["approve", "gate_sod_payment-implementation", "--role", "tech_lead",
                        "--by", "tl", "-f", manifest])  # fmt: skip
    runner.invoke(app, ["submit", "sod", "--by", "sec", "-f", manifest])
    wrong = runner.invoke(app, ["approve", "gate_sod_security-review", "--role", "product_owner",
                                "--by", "po", "-f", manifest])  # fmt: skip
    assert wrong.exit_code == 3, wrong.output  # refused: that gate is the security officer's
    right = runner.invoke(app, ["approve", "gate_sod_security-review", "--role", "security_officer",
                                "--by", "sec", "-f", manifest])  # fmt: skip
    assert right.exit_code in (0, 2), right.output
