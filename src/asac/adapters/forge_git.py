"""Generic git adapter for the Forge port: works with any remote reachable by the git CLI.

It keeps a private clone under ``cache_dir``. There are no change requests on plain git, so
``open_change_request`` raises ``Unsupported``; the portal then shows the pushed branch instead.
Git runs without a shell, without prompts, and never with ``--force``.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path, PurePosixPath

from asac.ports.forge import (
    Author,
    Capabilities,
    ChangeRequest,
    Conflict,
    FileContent,
    ForgeError,
    NotFound,
    Unsupported,
)

BRANCH = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,100}$")


def _safe_path(path: str) -> str:
    p = PurePosixPath(path)
    if p.is_absolute() or ".." in p.parts or not p.parts or "\x00" in path:
        raise ForgeError(f"refused path: {path!r}")
    return str(p)


def _safe_branch(name: str) -> str:
    if not BRANCH.match(name) or ".." in name or name.endswith(("/", ".lock")):
        raise ForgeError(f"refused branch name: {name!r}")
    return name


class GitForge:
    def __init__(self, remote: str, cache_dir: Path, default_branch: str | None = None) -> None:
        self.remote = remote
        self.dir = cache_dir
        self._default = default_branch
        self.dir.mkdir(parents=True, exist_ok=True)

    # --- plumbing -----------------------------------------------------------------------

    def _git(
        self, *args: str, cwd: Path | None = None, check: bool = True, raw: bool = False
    ) -> str:
        env = {
            "PATH": os.environ.get("PATH", ""),
            "HOME": str(self.dir),
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_CONFIG_NOSYSTEM": "1",
            "LC_ALL": "C",
        }
        try:
            done = subprocess.run(  # noqa: S603 (fixed argv, no shell)
                ["git", *args], cwd=cwd or self.dir, env=env, capture_output=True, text=True,
                timeout=120, check=False,
            )  # fmt: skip
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ForgeError(f"git failed: {type(exc).__name__}") from None
        if check and done.returncode != 0:
            raise ForgeError(f"git {args[0]} failed: {done.stderr.strip().splitlines()[-1:]}")
        if done.returncode != 0:
            return ""
        return done.stdout if raw else done.stdout.strip()

    def _sync(self) -> None:
        if not (self.dir / ".git").is_dir():
            self.dir.mkdir(parents=True, exist_ok=True)
            self._git("init", "-q", cwd=self.dir)
            self._git("remote", "add", "origin", self.remote)
        self._git("fetch", "-q", "--prune", "origin", "+refs/heads/*:refs/remotes/origin/*")

    def _rev(self, branch: str) -> str:
        sha = self._git("rev-parse", "--verify", "-q", f"refs/remotes/origin/{branch}", check=False)
        if not sha:
            raise NotFound(f"unknown branch: {branch}")
        return sha

    # --- Forge --------------------------------------------------------------------------

    def capabilities(self) -> Capabilities:
        return Capabilities(change_requests=False, members=False, webhooks=False)

    def default_branch(self) -> str:
        if self._default:
            return self._default
        out = self._git("ls-remote", "--symref", self.remote, "HEAD")
        m = re.match(r"ref: refs/heads/(\S+)\s+HEAD", out)
        if not m:
            raise ForgeError("cannot find the default branch")
        return m.group(1)

    def head(self, branch: str) -> str:
        self._sync()
        return self._rev(_safe_branch(branch))

    def read_file(self, path: str, branch: str | None = None) -> FileContent:
        path = _safe_path(path)
        self._sync()
        sha = self._rev(_safe_branch(branch or self.default_branch()))
        if not self._git("ls-tree", sha, "--", path, check=False):
            raise NotFound(f"no such file: {path}")
        shown = self._git("cat-file", "-p", f"{sha}:{path}", raw=True)
        return FileContent(path=path, content=shown, commit=sha)

    def create_branch(self, name: str, from_sha: str) -> None:
        name = _safe_branch(name)
        if not re.fullmatch(r"[0-9a-f]{40}", from_sha):
            raise ForgeError("from_sha must be a full commit id")
        self._sync()
        if self._git("rev-parse", "--verify", "-q", f"refs/remotes/origin/{name}", check=False):
            raise ForgeError(f"branch already exists: {name}")
        self._git("push", "-q", "origin", f"{from_sha}:refs/heads/{name}")

    def commit_files(
        self, branch: str, files: dict[str, str], message: str, author: Author, base_sha: str
    ) -> str:
        branch = _safe_branch(branch)
        self._sync()
        current = self._rev(branch)
        if current != base_sha:
            raise Conflict(f"{branch} moved since the draft was based on it", current)
        clean = {_safe_path(p): c for p, c in files.items()}
        self._git("checkout", "-q", "--detach", current)
        self._git("reset", "-q", "--hard", current)
        for rel, text in clean.items():
            target = self.dir / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
            self._git("add", "--", rel)
        ident = f"{author.name} <{author.email}>"
        self._git(
            "-c", f"user.name={author.name}", "-c", f"user.email={author.email}",
            "commit", "-q", "-m", f"{message}\n\nAuthored-via: ASAC portal on behalf of {ident}",
            "--author", ident,
        )  # fmt: skip
        new = self._git("rev-parse", "HEAD")
        # No --force: the push fails if someone moved the branch after our check.
        self._git("push", "-q", "origin", f"{new}:refs/heads/{branch}")
        return new

    def open_change_request(
        self, source: str, target: str, title: str, description: str
    ) -> ChangeRequest:
        raise Unsupported("plain git has no change requests; use the GitLab or GitHub adapter")

    def get_change_request(self, cr_id: str) -> ChangeRequest:
        raise Unsupported("plain git has no change requests")
