"""Runner adapters: an in-memory double for tests and a Docker container runner."""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from asac.ports.runner import ExecResult, Runner


def _asac_version() -> str:
    from asac import __version__

    return __version__


# The image a delegated step runs in. Build it with `docker build` on `asac/docker/agent`
# (the command is in the Dockerfile and in `asac doctor`); its tag carries ASAC's version.
IMAGE_NAME = "asac-agent"
DEFAULT_IMAGE = f"{IMAGE_NAME}:{_asac_version()}"
WORKTREE_MOUNT = "/work"


@dataclass
class FakeRunner:
    """Deterministic runner. ``up=False`` simulates a pool with no capacity."""

    up: bool = True
    results: list[ExecResult] = field(default_factory=list)  # consumed in order by exec()
    executed: list[list[str]] = field(default_factory=list)
    started: list[tuple[str, str]] = field(default_factory=list)
    stopped: list[str] = field(default_factory=list)

    def available(self) -> bool:
        return self.up

    def start(self, run_id: str, step_id: str) -> str:
        self.started.append((run_id, step_id))
        return f"fake-{run_id}-{step_id}"

    def exec(self, handle: str, argv: list[str], timeout: int) -> ExecResult:
        self.executed.append(list(argv))
        return self.results.pop(0) if self.results else ExecResult(0, "fake output\n")

    def stop(self, handle: str) -> None:
        self.stopped.append(handle)


def container_name(run_id: str, step_id: str) -> str:
    safe = "".join(c if c.isalnum() or c in "_.-" else "-" for c in f"asac-{run_id}-{step_id}")
    return safe[:63]


class DockerRunner:
    """Runs a step in a locked-down container: no network, read-only root, non-root user.

    The container sees **one** folder from the host: the run's worktree, mounted writable at
    ``/work``. The main checkout (``asac.yaml``, ``.asac/``, the hook scripts) and the state
    folder are never mounted, so the agent cannot read or change the rules. ``/tmp`` is a small
    tmpfs for the tool's own scratch files.
    """

    def __init__(
        self,
        root: Path,
        image: str = DEFAULT_IMAGE,
        docker: str | None = None,
        cpus: str = "1",
        memory: str = "512m",
        network: str = "none",
        env: dict[str, str] | None = None,
        worktree_for: Callable[[str], Path | None] | None = None,
    ) -> None:
        self.root, self.image, self.cpus, self.memory = root, image, cpus, memory
        self.network = network  # "none", or a Docker network the operator prepared
        self.env = dict(env or {})  # names only on the command line; values come from the process
        self.docker = docker or shutil.which("docker")
        # The folder given to the container for a run: the run's worktree. The engine sets it.
        # Without it the container gets ``root`` as is (a caller that picks the folder itself).
        self.worktree_for = worktree_for

    def command(self, run_id: str, step_id: str) -> list[str]:
        """The exact ``docker run`` line. Pure, so it is unit-tested without a daemon."""
        mounted = self.worktree_for(run_id) if self.worktree_for is not None else self.root
        if mounted is None:
            # Never fall back to the main checkout: it holds the rules the agent must not touch.
            raise RuntimeError(f"run '{run_id}' has no worktree to give the container")
        return [
            self.docker or "docker",
            "run", "--detach", "--rm",
            "--name", container_name(run_id, step_id),
            "--network", self.network,
            "--read-only",
            "--user", "65534:65534",
            "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges",
            "--pids-limit", "128",
            "--cpus", self.cpus,
            "--memory", self.memory,
            "--tmpfs", "/tmp:rw,size=64m,uid=65534,gid=65534",
            "--mount", f"type=bind,source={mounted},target={WORKTREE_MOUNT}",
            "--env", f"ASAC_RUN_ID={run_id}",
            "--env", f"ASAC_STEP={step_id}",
            *[a for name in sorted(self.env) for a in ("--env", name)],
            "--workdir", WORKTREE_MOUNT,
            self.image,
            "sleep", "3600",
        ]  # fmt: skip

    def available(self) -> bool:
        if not self.docker:
            return False
        try:
            proc = subprocess.run(
                [self.docker, "info", "--format", "{{.ServerVersion}}"],
                capture_output=True, timeout=10, check=False,
            )  # fmt: skip
        except (OSError, subprocess.TimeoutExpired):
            return False
        return proc.returncode == 0

    def start(self, run_id: str, step_id: str) -> str:
        proc = subprocess.run(
            self.command(run_id, step_id), capture_output=True, text=True, timeout=120, check=False
        )
        if proc.returncode != 0:
            raise RuntimeError(f"docker run failed: {proc.stderr.strip()}")
        return proc.stdout.strip()

    def exec(self, handle: str, argv: list[str], timeout: int) -> ExecResult:
        cmd = [self.docker or "docker", "exec", handle, *argv]
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout, check=False,
                env={**os.environ, **self.env},
            )  # fmt: skip
        except subprocess.TimeoutExpired as exc:
            out = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
            return ExecResult(124, self._redact(out), f"timed out after {timeout}s")
        return ExecResult(proc.returncode, self._redact(proc.stdout), self._redact(proc.stderr))

    def _redact(self, text: str) -> str:
        for value in self.env.values():
            if len(value) >= 4:
                text = text.replace(value, "[redacted]")
        return text

    def stop(self, handle: str) -> None:
        if self.docker:
            subprocess.run(
                [self.docker, "stop", handle], capture_output=True, timeout=60, check=False
            )


def runner_from_vars(
    root: Path,
    values: dict[str, str],
    worktree_for: Callable[[str], Path | None] | None = None,
) -> Runner | None:
    """``runner_kind: docker`` (vars file or ``ASAC_RUNNER=docker``) builds the Docker runner.

    ``runner_image``, ``runner_network`` (default none), ``runner_env`` (comma list of variable
    names passed through, e.g. a model API key: values are read from the process, never stored).
    """
    kind = os.environ.get("ASAC_RUNNER") or values.get("runner_kind", "")
    if not kind:
        return None
    if kind == "fake":  # a test double, like the fake harness: starts nothing, runs nothing
        return FakeRunner()
    if kind not in ("docker", "kubernetes"):
        raise RuntimeError(f"unknown runner_kind '{kind}' (available: docker, kubernetes)")
    names = [n.strip() for n in values.get("runner_env", "").split(",") if n.strip()]
    env = {n: os.environ[n] for n in names if n in os.environ}
    if kind == "kubernetes":
        from asac.adapters.runner_k8s import KubernetesRunner

        return KubernetesRunner(
            image=values.get("runner_image", DEFAULT_IMAGE),
            namespace=values.get("runner_k8s_namespace", "asac"),
            context=values.get("runner_k8s_context") or None,
            pvc=values.get("runner_k8s_pvc") or None,
            secret=values.get("runner_k8s_secret") or None,
            env=dict.fromkeys(names, "") | env,
        )
    return DockerRunner(
        root,
        image=values.get("runner_image", DEFAULT_IMAGE),
        network=values.get("runner_network", "none"),
        env=env,
        worktree_for=worktree_for,
    )
