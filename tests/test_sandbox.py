"""The sandbox wrapper: what ASAC asks of the OS sandbox, and what it refuses to do."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from asac.adapters.sandbox import SandboxError, SandboxPolicy, build_settings, wrap_command


def _policy(work: Path, **kw: object) -> SandboxPolicy:
    base = {
        "workdir": work,
        "allowed_domains": ("api.example-gateway.test",),
        "extra_write": (),
        "deny_read": ("~/.ssh", "~/.aws"),
    }
    base.update(kw)
    return SandboxPolicy(**base)  # type: ignore[arg-type]


def test_settings_allow_writes_only_in_the_worktree(tmp_path: Path) -> None:
    work = tmp_path / "wt"
    s = build_settings(_policy(work))
    # exactly the worktree, plus the scratch folder the Bash tool needs (spike B, reserve 2)
    writable = s["filesystem"]["allowWrite"]
    assert str(work) in writable
    assert all(
        p == str(work) or p.startswith("/private/tmp/claude") or p.startswith("/tmp/")
        for p in writable
    )
    assert str(tmp_path) not in writable or work == tmp_path  # the parent is not writable
    assert "~/.ssh" in s["filesystem"]["denyRead"]


def test_settings_network_is_a_domain_allowlist_with_a_deny_list(tmp_path: Path) -> None:
    s = build_settings(_policy(tmp_path / "wt"))
    assert s["network"]["allowedDomains"] == ["api.example-gateway.test"]
    assert s["network"]["deniedDomains"] == []  # required key: srt refuses a config without it


def test_no_allowed_domain_means_no_network(tmp_path: Path) -> None:
    s = build_settings(_policy(tmp_path / "wt", allowed_domains=()))
    assert s["network"]["allowedDomains"] == []


def test_wildcard_domains_are_refused(tmp_path: Path) -> None:
    """A wildcard allowlist is a hole: every subdomain of a public host becomes reachable."""
    with pytest.raises(SandboxError, match="wildcard"):
        build_settings(_policy(tmp_path / "wt", allowed_domains=("*",)))


def test_the_workdir_must_exist_and_be_absolute(tmp_path: Path) -> None:
    with pytest.raises(SandboxError, match="absolute"):
        build_settings(_policy(Path("relative/wt")))


def test_wrap_command_runs_claude_through_srt(tmp_path: Path) -> None:
    work = tmp_path / "wt"
    work.mkdir()
    argv = wrap_command(["claude", "-p", "go"], _policy(work), settings_path=tmp_path / "s.json")
    assert argv[0].endswith("srt")
    assert argv[1:3] == ["-s", str(tmp_path / "s.json")]
    assert argv[3:] == ["-c", "claude -p go"]  # one shell string: srt wraps a command line


def test_settings_file_is_plain_json(tmp_path: Path) -> None:
    s = build_settings(_policy(tmp_path / "wt"))
    assert json.loads(json.dumps(s)) == s


def test_arguments_with_spaces_and_quotes_are_quoted_for_the_shell(tmp_path: Path) -> None:
    """srt runs a shell string: a prompt with quotes must not break out of its argument."""
    import shlex

    work = tmp_path / "wt"
    work.mkdir()
    nasty = 'say "hi"; rm -rf ~ $(whoami) `id`'
    argv = wrap_command(["claude", "-p", nasty], _policy(work), settings_path=tmp_path / "s.json")
    shell_string = argv[-1]
    assert shlex.split(shell_string) == ["claude", "-p", nasty]  # round-trips exactly


def test_autorun_under_the_sandbox_launches_the_tool_through_srt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With the sandbox on, autorun runs claude inside srt, in the worktree, with the policy."""
    from asac.adapters import AdapterContext
    from asac.adapters.claude_code import ClaudeCodeHarness
    from asac.loader.load import load_manifest

    project = Path(__file__).resolve().parent.parent / "examples" / "payments-service"
    work = tmp_path / "wt"
    work.mkdir()
    calls: list[list[str]] = []

    def fake_run(argv, **kw):  # type: ignore[no-untyped-def]
        calls.append(list(argv))
        return type("P", (), {"returncode": 0, "stdout": "{}", "stderr": ""})()

    monkeypatch.setattr("asac.adapters.claude_code.subprocess.run", fake_run)
    h = ClaudeCodeHarness(
        AdapterContext(project, load_manifest(project / "asac.yaml"), tmp_path / "state",
                       autorun=True, work=work, sandbox=True)
    )  # fmt: skip
    h.permissions("assist")
    h.run({"step": "requirements", "capability": "c", "agent": "ba", "skill": "spec"},
          {"run_id": "r1"})  # fmt: skip
    assert calls, "autorun did not launch anything"
    launched = calls[0]
    assert launched[0].endswith("srt"), launched
    assert "claude" in launched[-1]


def test_the_sandbox_is_off_by_default_and_on_when_asked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from asac.engine.runtime import _domains, _flag

    monkeypatch.delenv("ASAC_SANDBOX", raising=False)
    assert _flag(None, False) is False  # not on by accident
    assert _flag("1", False) is True
    assert _domains("api.example.com, other.example.com", {}) == (
        "api.example.com", "other.example.com",
    )  # fmt: skip
    assert _domains(None, {"sandbox_domains": ["a.example.com"]}) == ("a.example.com",)
    assert _domains(None, {}) == ()  # no domain listed: no network at all
