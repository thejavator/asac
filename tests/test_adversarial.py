"""An agent that tries to cheat. Each attempt must fail, and the rules it targets must be intact.

These tests run a stand-in tool (a shell script) under the real OS sandbox (srt) and check the
disk afterwards, not what the tool says about itself.
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from asac.cli import app
from asac.engine.runtime import store_for
from tests.conftest import init_git

SRT = shutil.which("srt")


def _node_ok() -> bool:
    """srt needs Node >= 22.12; an older node on PATH makes it crash and proves nothing."""
    from asac.doctor import MIN_NODE, parse_node_version

    node = shutil.which("node")
    if node is None:
        return False
    out = subprocess.run([node, "--version"], capture_output=True, text=True).stdout
    got = parse_node_version(out)
    return got is not None and got >= MIN_NODE


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(SRT is None, reason="srt (sandbox-runtime) is not installed"),
    pytest.mark.skipif(not _node_ok(), reason="node >= 22.12 is needed by srt"),
]
runner = CliRunner()
EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "real-tools"


def asac(root: Path, *args: str):  # type: ignore[no-untyped-def]
    return runner.invoke(app, [*args, "-f", str(root / "asac.yaml")])


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def arena(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """real-tools under git, with the sandbox on and a hostile stand-in as the `claude` tool."""
    root = tmp_path / "proj"
    shutil.copytree(EXAMPLE, root)
    shutil.copy(root / "vars" / "claude-code.yaml", root / "asac.vars.yaml")
    init_git(root)
    bindir = tmp_path / "bin"
    bindir.mkdir()
    secret = tmp_path / "home" / ".ssh"
    secret.mkdir(parents=True)
    (secret / "id_rsa").write_text("PRIVATE-KEY-MATERIAL")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("ASAC_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("ASAC_FIXED_TIME", "2026-01-01T00:00:00Z")
    monkeypatch.setenv("ASAC_AUTORUN", "1")
    monkeypatch.setenv("ASAC_SANDBOX", "1")
    monkeypatch.setenv("ASAC_SANDBOX_DOMAINS", "api.example-gateway.test")
    node_dir = Path(shutil.which("node") or "").parent  # the node doctor just accepted
    monkeypatch.setenv("PATH", f"{bindir}:{node_dir}:{Path(SRT or '').parent}:/usr/bin:/bin")
    (tmp_path / "bin_dir").write_text(str(bindir))
    return root


def hostile_tool(tmp_path: Path, body: str) -> None:
    bindir = Path((tmp_path / "bin_dir").read_text())
    tool = bindir / "claude"
    ok = (
        'echo \'{"type":"result","is_error":false,"total_cost_usd":0.01,'
        '"usage":{},"result":"done"}\'\n'
    )
    # The marker proves the tool ran at all: an attack that "fails" because nothing ran is void.
    tool.write_text("#!/bin/sh\necho TOOL-RAN >&2\n" + body + "\n" + ok)
    tool.chmod(0o755)


def ran(tmp_path: Path, run_id: str) -> bool:
    """ASAC audited the launch, and the tool's own log shows it executed (it prints TOOL-RAN)."""
    log = tmp_path / "state" / "briefs" / run_id / "requirements.log"
    return log.is_file() and "TOOL-RAN" in log.read_text()


def _git(cwd: Path, *a: str) -> str:
    return subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True).stdout.strip()


def test_tampering_with_a_hook_leaves_the_real_hook_intact(arena: Path, tmp_path: Path) -> None:
    """The tool tries to make the tests-green hook pass by rewriting it. The rewrite fails."""
    hook = arena / ".asac" / "hooks" / "tests-green.sh"
    before = _digest(hook)
    state = tmp_path / "state"
    hostile_tool(
        tmp_path,
        f'echo "exit 0" > "{hook}" 2>/dev/null; '
        f'printf "# Spec\\n## Acceptance criteria\\n- ok\\n" > SPEC.md',
    )
    asac(arena, "apply", "-p", "feature", "--run-id", "h1")
    assert ran(tmp_path, "h1"), "the hostile tool never ran: this test proves nothing"
    assert _digest(hook) == before, "the hook in the main checkout was rewritten"
    assert state.exists()


def test_the_manifest_cannot_be_rewritten(arena: Path, tmp_path: Path) -> None:
    manifest = arena / "asac.yaml"
    before = _digest(manifest)
    hostile_tool(tmp_path, f'echo "# hacked" >> "{manifest}" 2>/dev/null; true')
    asac(arena, "apply", "-p", "feature", "--run-id", "m1")
    assert ran(tmp_path, "m1"), "the hostile tool never ran: this test proves nothing"
    assert _digest(manifest) == before


def test_the_audit_database_cannot_be_deleted(arena: Path, tmp_path: Path) -> None:
    db = tmp_path / "state" / "state.db"
    hostile_tool(
        tmp_path, f'rm -f "{db}" 2>/dev/null; rm -rf "{tmp_path / "state"}" 2>/dev/null; true'
    )
    asac(arena, "apply", "-p", "feature", "--run-id", "a1")
    assert ran(tmp_path, "a1"), "the hostile tool never ran: this test proves nothing"
    assert db.exists(), "the state database was deleted by the tool"
    assert "run.created" in asac(arena, "logs", "a1").output


def test_private_keys_are_not_readable(arena: Path, tmp_path: Path) -> None:
    stolen = tmp_path / "state" / "worktrees" / "k1" / "stolen.txt"
    key = tmp_path / "home" / ".ssh" / "id_rsa"
    hostile_tool(tmp_path, f'cat "{key}" > stolen.txt 2>/dev/null; true')
    asac(arena, "apply", "-p", "feature", "--run-id", "k1")
    assert ran(tmp_path, "k1"), "the hostile tool never ran: this test proves nothing"
    assert not stolen.exists() or "PRIVATE-KEY-MATERIAL" not in stolen.read_text()


def test_writing_outside_the_worktree_is_refused(arena: Path, tmp_path: Path) -> None:
    outside = tmp_path / "ESCAPED.txt"
    hostile_tool(tmp_path, f'echo x > "{outside}" 2>/dev/null; true')
    asac(arena, "apply", "-p", "feature", "--run-id", "w1")
    assert ran(tmp_path, "w1"), "the hostile tool never ran: this test proves nothing"
    assert not outside.exists()


def test_a_domain_that_is_not_allowed_is_unreachable(arena: Path, tmp_path: Path) -> None:
    hostile_tool(
        tmp_path,
        "curl -s -o /dev/null --max-time 8 https://www.wikipedia.org "
        "&& echo REACHED > reached.txt || echo BLOCKED > reached.txt",
    )
    asac(arena, "apply", "-p", "feature", "--run-id", "n1")
    assert ran(tmp_path, "n1"), "the hostile tool never ran: this test proves nothing"
    marker = tmp_path / "state" / "worktrees" / "n1" / "reached.txt"
    assert marker.read_text().strip() == "BLOCKED"


# -- the refusals are in the audit (the scope's criterion) -------------------------------------


def _denied(tmp_path: Path, run_id: str) -> list[str]:
    return [
        a.detail for a in store_for(tmp_path / "proj" / "asac.yaml").audit(run_id)
        if a.action == "sandbox.denied"
    ]  # fmt: skip


def test_a_refused_write_to_a_hook_is_in_the_audit(arena: Path, tmp_path: Path) -> None:
    hook = arena / ".asac" / "hooks" / "tests-green.sh"
    hostile_tool(tmp_path, f'echo "exit 0" > "{hook}"')
    asac(arena, "apply", "-p", "feature", "--run-id", "da1")
    assert ran(tmp_path, "da1")
    assert any(str(hook.name) in d and d.startswith("filesystem") for d in _denied(tmp_path, "da1"))


def test_a_refused_read_of_a_key_is_in_the_audit(arena: Path, tmp_path: Path) -> None:
    key = tmp_path / "home" / ".ssh" / "id_rsa"
    hostile_tool(tmp_path, f'cat "{key}"')
    asac(arena, "apply", "-p", "feature", "--run-id", "da2")
    assert ran(tmp_path, "da2")
    assert f"filesystem {key}" in _denied(tmp_path, "da2")


def test_a_refused_deletion_of_the_state_is_in_the_audit(arena: Path, tmp_path: Path) -> None:
    db = tmp_path / "state" / "state.db"
    hostile_tool(tmp_path, f'rm -f "{db}"')
    asac(arena, "apply", "-p", "feature", "--run-id", "da3")
    assert ran(tmp_path, "da3")
    assert any("state.db" in d for d in _denied(tmp_path, "da3"))


def test_a_refused_connection_to_a_host_is_in_the_audit(arena: Path, tmp_path: Path) -> None:
    hostile_tool(tmp_path, "curl -s -o /dev/null --max-time 8 https://www.wikipedia.org")
    asac(arena, "apply", "-p", "feature", "--run-id", "da4")
    assert ran(tmp_path, "da4")
    assert "network www.wikipedia.org:443" in _denied(tmp_path, "da4")


def test_a_clean_run_records_no_denial(arena: Path, tmp_path: Path) -> None:
    hostile_tool(tmp_path, 'printf "# Spec\\n## Acceptance criteria\\n- ok\\n" > SPEC.md')
    asac(arena, "apply", "-p", "feature", "--run-id", "da5")
    assert _denied(tmp_path, "da5") == []


def test_the_default_audit_view_says_what_was_refused(arena: Path, tmp_path: Path) -> None:
    """`asac audit` printed "sandbox.denied" four times and nothing else: a reviewer could not
    tell a refused read of a key from a refused connection."""
    key = tmp_path / "home" / ".ssh" / "id_rsa"
    hostile_tool(tmp_path, f'cat "{key}"')
    asac(arena, "apply", "-p", "feature", "--run-id", "dv1")
    out = asac(arena, "audit", "--run-id", "dv1").output
    line = next(ln for ln in out.splitlines() if "sandbox.denied" in ln)
    assert str(key) in line, line
