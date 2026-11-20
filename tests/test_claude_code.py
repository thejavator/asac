from pathlib import Path

import pytest
import yaml

from asac.adapters import AdapterContext
from asac.adapters.base import HarnessError
from asac.adapters.claude_code import BEGIN, END, ClaudeCodeHarness
from asac.loader.load import load_manifest


def harness(project: Path, tmp_path: Path) -> ClaudeCodeHarness:
    return ClaudeCodeHarness(
        AdapterContext(project, load_manifest(project / "asac.yaml"), tmp_path / "state")
    )


def test_mount_writes_valid_skill_file(sandbox_project: Path, tmp_path: Path) -> None:
    harness(sandbox_project, tmp_path).mount("spec")
    text = (sandbox_project / ".claude/skills/spec/SKILL.md").read_text()
    assert text.startswith("---\n")  # frontmatter must be the first line
    front = yaml.safe_load(text.split("---")[1])
    assert front["name"] == "spec"
    assert front["description"]
    assert "security" in text.lower()  # project instructions are embedded


def test_mount_is_idempotent_and_keeps_user_claude_md(
    sandbox_project: Path, tmp_path: Path
) -> None:
    md = sandbox_project / "CLAUDE.md"
    md.write_text("# My notes\n\nKeep this.\n")
    h = harness(sandbox_project, tmp_path)
    h.mount("spec")
    h.mount("spec")
    h.mount("java-impl")
    text = md.read_text()
    assert text.startswith("# My notes") and "Keep this." in text
    assert text.count(BEGIN) == 1 and text.count(END) == 1
    assert "/java-impl" in text and "/spec" in text


def test_unknown_or_unsafe_skill_refused(sandbox_project: Path, tmp_path: Path) -> None:
    h = harness(sandbox_project, tmp_path)
    with pytest.raises(HarnessError):
        h.mount("../evil")
    with pytest.raises(HarnessError):
        h.mount("nope")
    assert not (sandbox_project.parent / "evil").exists()


def test_delegate_returns_headless_command_for_the_runner(
    sandbox_project: Path, tmp_path: Path
) -> None:
    h = harness(sandbox_project, tmp_path)
    h.permissions("delegate")
    r = h.run(
        {"step": "s", "capability": "c", "agent": "a", "skill": "x", "mode": "delegate"},
        {"run_id": "r1"},
    )
    assert r["status"] == "delegated" and r["exec"][:2] == ["claude", "-p"]
    assert "--permission-mode" in r["exec"]


def test_run_writes_brief_and_hands_off(sandbox_project: Path, tmp_path: Path) -> None:
    h = harness(sandbox_project, tmp_path)
    r = h.run(
        {
            "step": "requirements",
            "capability": "c",
            "agent": "ba",
            "skill": "spec",
            "produces": ["spec_reviewed"],
        },
        {"run_id": "run1"},
    )
    assert r["status"] == "handoff"
    brief = Path(r["brief"]).read_text()
    assert "spec_reviewed" in brief and "/spec" in brief


def _with_mcp(project: Path, tmp_path: Path) -> ClaudeCodeHarness:
    f = project / "asac.yaml"
    data = yaml.safe_load(f.read_text())
    data["providers"]["jira"]["mcp"] = {
        "command": "jira-mcp",
        "args": ["--stdio"],
        "env": {"JIRA_TOKEN": "${vault.jira/token}"},
    }
    data["providers"]["gitlab"]["mcp"] = {"url": "https://gitlab.example.com/mcp"}
    f.write_text(yaml.safe_dump(data))
    return harness(project, tmp_path)


def test_mcp_config_has_only_the_steps_servers_and_no_secret(
    sandbox_project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import json

    monkeypatch.setenv("ASAC_VAULT_JIRA_TOKEN", "s3cr3t-value")
    h = _with_mcp(sandbox_project, tmp_path)
    h.tools(["jira"])
    raw = (sandbox_project / ".mcp.json").read_text()
    doc = json.loads(raw)
    assert list(doc["mcpServers"]) == ["jira"]  # gitlab is not exposed to this step
    assert doc["mcpServers"]["jira"]["env"] == {"JIRA_TOKEN": "${ASAC_VAULT_JIRA_TOKEN}"}
    assert "s3cr3t-value" not in raw
    ev = [e for e in h.events if e["event"] == "tools.exposed"][0]
    assert ev["servers"] == ["jira"] and "s3cr3t-value" not in str(h.events)
    argv = h.command("go", False)
    assert argv is not None
    assert argv[-3:] == ["--strict-mcp-config", "--allowedTools", "mcp__jira__*"] or (
        "--strict-mcp-config" in argv and argv[-1] == "mcp__jira__*"
    )


def test_mcp_without_servers_leaves_command_unchanged_and_removes_managed_file(
    sandbox_project: Path, tmp_path: Path
) -> None:
    h = _with_mcp(sandbox_project, tmp_path)
    h.tools(["gitlab"])
    assert (sandbox_project / ".mcp.json").is_file()
    h.tools([])
    assert not (sandbox_project / ".mcp.json").exists()
    assert h.command("go", True) == ["claude", "-p", "go", "--permission-mode", "plan"]


def test_mcp_refuses_to_overwrite_a_user_file(sandbox_project: Path, tmp_path: Path) -> None:
    (sandbox_project / ".mcp.json").write_text('{"mcpServers": {}}')
    h = _with_mcp(sandbox_project, tmp_path)
    with pytest.raises(HarnessError):
        h.tools(["jira"])


@pytest.mark.parametrize(
    "cls_name,head",
    [("CodexHarness", ["codex", "exec"]), ("CursorHarness", ["cursor-agent", "-p"])],
)
def test_other_headless_harnesses_return_their_command(
    cls_name: str, head: list[str], sandbox_project: Path, tmp_path: Path
) -> None:
    from asac.adapters import file_mount

    h = harness(sandbox_project, tmp_path)
    h2 = getattr(file_mount, cls_name)(h._ctx)
    h2.permissions("delegate")
    r = h2.run(
        {"step": "s", "capability": "c", "agent": "a", "skill": "x", "mode": "delegate"},
        {"run_id": "r1"},
    )
    assert r["status"] == "delegated" and r["exec"][:2] == head


def test_delegate_without_headless_command_is_refused(
    sandbox_project: Path, tmp_path: Path
) -> None:
    from asac.adapters.file_mount import BobHarness

    h = BobHarness(harness(sandbox_project, tmp_path)._ctx)
    h.permissions("delegate")
    with pytest.raises(HarnessError, match="no headless command"):
        h.run(
            {"step": "s", "capability": "c", "agent": "a", "skill": "x", "mode": "delegate"},
            {"run_id": "r1"},
        )
