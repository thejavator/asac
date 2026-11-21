"""``asac doctor``: check the prerequisites of a run before it fails halfway through."""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

MIN_NODE = (22, 12, 0)  # what srt (sandbox-runtime) requires


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str
    required: bool = True  # a missing optional tool is reported but does not fail the command


def parse_node_version(text: str) -> tuple[int, int, int] | None:
    m = re.match(r"\s*v?(\d+)\.(\d+)\.(\d+)", text)
    return (int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None


def _node_version() -> str:
    node = shutil.which("node")
    if node is None:
        return ""
    proc = subprocess.run([node, "--version"], capture_output=True, text=True, timeout=10)
    return proc.stdout.strip()


def check_tool(name: str, hint: str, required: bool = True) -> Check:
    path = shutil.which(name)
    if path is None:
        return Check(name, False, f"not found. Install it: {hint}", required)
    return Check(name, True, path, required)


def check_node() -> Check:
    raw = _node_version()
    if not raw:
        return Check("node", False, "not found. srt needs Node >= 22.12: brew install node")
    got = parse_node_version(raw)
    need = ".".join(map(str, MIN_NODE))
    if got is None or got < MIN_NODE:
        return Check("node", False, f"{raw.lstrip('v')} is too old; srt needs Node >= {need}")
    return Check("node", True, raw.lstrip("v"))


def check_git_repo(root: Path) -> Check:
    def git(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, timeout=30)

    if shutil.which("git") is None or git("rev-parse", "--is-inside-work-tree").returncode != 0:
        return Check("git repository", False, f"{root} is not a git repository: run `git init`")
    if git("rev-parse", "--verify", "HEAD").returncode != 0:
        return Check("git repository", False, "no commit yet: commit your files first")
    if git("status", "--porcelain").stdout.strip():
        return Check("git repository", False, "uncommitted changes: a run starts from HEAD, "
                     "so they would not be part of what the agent works on")  # fmt: skip
    return Check("git repository", True, "clean, with at least one commit")


def run_checks(root: Path) -> list[Check]:
    return [
        check_tool("git", "install git"),
        check_tool("opa", "brew install opa"),
        check_node(),
        check_tool("srt", "npm install -g @anthropic-ai/sandbox-runtime"),
        check_tool(
            "claude",
            "see https://docs.claude.com/claude-code (only for Claude Code)",
            required=False,
        ),  # fmt: skip
        check_git_repo(root),
    ]
