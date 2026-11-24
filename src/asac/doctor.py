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
    # .asac-state/ is ASAC's own folder (the default state): after a first run it is untracked,
    # and a run copies from HEAD, so it is never part of what the agent works on.
    dirty = [
        line for line in git("status", "--porcelain").stdout.splitlines()
        if not line[3:].startswith(".asac-state")
    ]  # fmt: skip
    if dirty:
        return Check("git repository", False, "uncommitted changes: a run starts from HEAD, "
                     "so they would not be part of what the agent works on")  # fmt: skip
    return Check("git repository", True, "clean, with at least one commit")


def _docker(*args: str) -> subprocess.CompletedProcess[str] | None:
    """A docker command that cannot hang the command: a stuck daemon counts as absent."""
    docker = shutil.which("docker")
    if docker is None:
        return None
    try:
        return subprocess.run([docker, *args], capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        return None


def agent_image_build_command(image: str) -> str:
    """The command that builds the agent image from the Dockerfile shipped with ASAC."""
    from asac import __version__

    context = Path(__file__).resolve().parent / "docker" / "agent"
    return f"docker build -t {image} --build-arg ASAC_VERSION={__version__} {context}"


def check_agent_image(image: str) -> Check:
    """The image a delegated step runs in. Optional: only ``mode: delegate`` needs it."""
    proc = _docker("image", "inspect", image)
    if proc is None:
        return Check("agent image", False, "docker does not answer: delegated steps need it", False)
    if proc.returncode != 0:
        return Check("agent image", False, f"{image} not built. Build it: "
                     f"{agent_image_build_command(image)}", False)  # fmt: skip
    return Check("agent image", True, image, False)


def check_runner_network(name: str) -> Check:
    """A runner network the operator named must exist: the container would not start otherwise."""
    proc = _docker("network", "inspect", name)
    if proc is None:
        return Check("runner network", False, "docker does not answer", False)
    if proc.returncode != 0:
        hint = f"network '{name}' not found. Create it (docker network create {name})"
        return Check("runner network", False, f"{hint} and route it to the model gateway", False)
    return Check("runner network", True, name, False)


def _runner_settings(root: Path) -> tuple[str, str]:
    """(image, network) the Docker runner will use: the vars file, then the defaults."""
    from asac.adapters.runner_local import DEFAULT_IMAGE

    values: dict[str, object] = {}
    path = root / "asac.vars.yaml"
    if path.is_file():
        from asac.loader.load import load_vars

        values = dict(load_vars(path).values)
    return (str(values.get("runner_image", DEFAULT_IMAGE)),
            str(values.get("runner_network", "none")))  # fmt: skip


def run_checks(root: Path) -> list[Check]:
    image, network = _runner_settings(root)
    extra = [check_runner_network(network)] if network not in ("none", "") else []
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
        check_agent_image(image),
        *extra,
    ]
