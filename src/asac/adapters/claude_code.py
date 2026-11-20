"""Claude Code adapter (assist; delegate through a Runner).

``mount`` projects an ASAC skill into the native format:
``.claude/skills/<skill>/SKILL.md`` plus a managed block in ``CLAUDE.md``.
In assist mode ``run`` does not call a model: it writes a task brief and hands the work to the
developer. In delegate mode it returns the headless command for the engine to run in a Runner.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

from asac.adapters.base import AdapterContext, HarnessError, safe_name, write_brief
from asac.adapters.vault import env_name
from asac.catalog import HARNESSES
from asac.ports.harness import HarnessDescriptor

MCP_FILE = ".mcp.json"
BEGIN = "<!-- asac:begin (managed by asac, do not edit) -->"
END = "<!-- asac:end -->"


class ClaudeCodeHarness:
    harness_id = "claude-code"
    tool_name = "Claude Code"
    launch_hint = "claude"

    def __init__(self, ctx: AdapterContext) -> None:
        self._ctx = ctx
        self._mounted: list[str] = []
        self._mode = "assist"
        self._mcp: list[str] = []  # servers exposed to the current step
        self.events: list[dict[str, Any]] = []

    # -- port ---------------------------------------------------------------
    def mount(self, skill: str) -> None:
        manifest = self._ctx.manifest
        if skill not in manifest.skills:
            raise HarnessError(f"unknown skill '{skill}'")
        name = safe_name(skill)
        target = self._ctx.root / ".claude" / "skills" / name / "SKILL.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self._skill_md(name), encoding="utf-8")
        if name not in self._mounted:
            self._mounted.append(name)
        self._write_claude_md()

    def run(self, task: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        if self._mode not in ("assist", "readonly", "delegate"):
            raise HarnessError(f"unknown mode '{self._mode}'")
        lines = [
            f"# Task: {task['step']}",
            "",
            f"- run: {context.get('run_id', '?')}",
            f"- capability: {task['capability']}",
            f"- agent: {task['agent']}",
            f"- skill: {task['skill']} (mounted: {self.mounted_path(task['skill'])})",
            "",
            *(
                ["**Read-only step: do not modify files, branches or tickets.**", ""]
                if self._mode == "readonly"
                else []
            ),
            "## Evidence this step must produce",
            *[f"- {e}" for e in task.get("produces", [])],
            "",
            f"Open {self.tool_name} in this repository (e.g. `{self.launch_hint}`), "
            "do the work, then continue with "
            "`asac approve <gate-id>` and `asac apply --resume <run-id>`.",
        ]
        run_id = str(context.get("run_id", "run"))
        text = "\n".join(lines) + "\n"
        path = write_brief(self._ctx, run_id, task["step"], text)
        if self._mode == "delegate":
            # The runner executes the command; the engine captures and audits the output.
            prompt = (
                f"You are the '{task['agent']}' agent of an ASAC pipeline, running unattended. "
                f"Do the work of the step '{task['step']}' only.\n\n{text}"
            )
            argv = self.command(prompt, False)
            if argv is None:
                raise HarnessError(
                    f"{self.tool_name} has no headless command: use mode: assist for this step"
                )
            return {"status": "delegated", "brief": str(path), "exec": argv}
        result: dict[str, Any] = {"status": "handoff", "brief": str(path)}
        if self._ctx.autorun:
            launched = self._autorun(task, path)
            if launched is not None:
                result["autorun"] = launched
        return result

    def command(self, prompt: str, readonly: bool) -> list[str] | None:
        """Non-interactive command for this tool, or None for GUI-only tools."""
        mode = "plan" if readonly else "acceptEdits"
        argv = ["claude", "-p", prompt, "--permission-mode", mode]
        if self._mcp:
            argv += [
                "--mcp-config", MCP_FILE, "--strict-mcp-config",
                "--allowedTools", ",".join(f"mcp__{n}__*" for n in self._mcp),
            ]  # fmt: skip
        return argv

    def _autorun(self, task: dict[str, Any], brief: Path) -> dict[str, str] | None:
        """Opt-in (vars `autorun: true` or ASAC_AUTORUN=1): launch the tool, return what to audit.

        The result is checked by the step's hooks and a person decides at the gate.
        """
        step = task["step"]
        prompt = (
            f"You are the '{task['agent']}' agent of an ASAC pipeline. Read the brief "
            f"{brief} and the mounted skill ({self.mounted_path(task['skill'])}), then do the "
            f"work of the step '{step}' only. Do not do the work of any other step."
        )
        cmd = self.command(prompt, self._mode == "readonly")
        if cmd is None:
            return None  # GUI tool: nothing to launch, the person opens it
        log = brief.with_suffix(".log")
        timeout = self._ctx.autorun_timeout
        try:
            done = subprocess.run(  # noqa: S603 - fixed argv, no shell
                cmd, cwd=self._ctx.root, capture_output=True, text=True, timeout=timeout,
                stdin=subprocess.DEVNULL,
            )  # fmt: skip
        except FileNotFoundError:
            raise HarnessError(f"'{cmd[0]}' is not installed or not on PATH") from None
        except subprocess.TimeoutExpired:
            raise HarnessError(f"'{cmd[0]}' did not finish within {timeout}s") from None
        log.write_text(done.stdout + done.stderr, encoding="utf-8")
        if done.returncode != 0:
            raise HarnessError(f"'{cmd[0]}' exited with {done.returncode}; see {log}")
        digest = hashlib.sha256(log.read_bytes()).hexdigest()
        return {"tool": cmd[0], "exit": "0", "log": str(log), "log_sha256": digest}

    def mounted_path(self, skill: str) -> str:
        return f".claude/skills/{skill}/SKILL.md"

    def tools(self, mcp_servers: list[str]) -> None:
        """Write ``.mcp.json`` with only this step's servers; secrets stay as ``${ENV}``."""
        providers = self._ctx.manifest.providers
        servers: dict[str, Any] = {}
        env_names: list[str] = []
        for name in mcp_servers:
            mcp = providers[name].mcp if name in providers else None
            if mcp is None:
                continue
            entry: dict[str, Any] = {"command": mcp.command, "args": mcp.args} if mcp.command else {
                "type": "http", "url": mcp.url,
            }  # fmt: skip
            if mcp.env:
                names = {k: env_name(v) for k, v in mcp.env.items()}
                env_names += list(names.values())
                if mcp.command:
                    entry["env"] = {k: "${" + v + "}" for k, v in names.items()}
                else:
                    entry["headers"] = {k: "${" + v + "}" for k, v in names.items()}
            servers[name] = entry
        path = self._ctx.root / MCP_FILE
        if path.is_file() and "_asac" not in path.read_text(encoding="utf-8"):
            if servers:
                raise HarnessError(f"{MCP_FILE} exists and is not managed by asac")
            self._mcp = []
            return
        if servers:
            doc = {"_asac": "managed by asac, do not edit", "mcpServers": servers}
            path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
        elif path.is_file():
            path.unlink()
        self._mcp = list(servers)
        self.events.append(
            {
                "event": "tools.exposed",
                "servers": list(servers),
                "requested": list(mcp_servers),
                "env": sorted(set(env_names)),
                "wired": bool(servers),
            }
        )

    def permissions(self, mode: str) -> None:
        if mode not in ("assist", "delegate", "readonly"):
            raise HarnessError(f"unknown mode '{mode}'")
        self._mode = mode  # readonly: the brief tells the person not to change files

    def emit(self, event: dict[str, Any]) -> None:
        self.events.append(dict(event))

    def describe(self) -> HarnessDescriptor:
        return HARNESSES[self.harness_id]

    def health_check(self) -> bool:
        return self._ctx.root.is_dir()

    # -- rendering ----------------------------------------------------------
    def _skill_md(self, name: str) -> str:
        m = self._ctx.manifest
        skill = m.skills[name]
        cap = m.capabilities.get(skill.fulfils)
        desc = cap.description if cap and cap.description else f"ASAC skill {name}"
        desc = " ".join(desc.split())  # one line: frontmatter must stay valid YAML
        out = ["---", f"name: {name}", f"description: {_yaml_str(desc)}", "---", ""]
        out += [f"# {name}", "", f"Fulfils the `{skill.fulfils}` capability.", ""]
        if cap:
            for title, items in (
                ("Inputs", cap.inputs),
                ("Outputs", cap.outputs),
                ("Required evidence", cap.evidence),
            ):
                if items:
                    out += [f"## {title}", *[f"- {i}" for i in items], ""]
        if skill.params:
            out += ["## Parameters", *[f"- {k}: {v}" for k, v in sorted(skill.params.items())], ""]
        out += [f"Source: `{skill.ref}`", ""]
        src = self._ctx.root / skill.ref
        inside = src.is_file() and src.resolve().is_relative_to(self._ctx.root.resolve())
        if inside and not skill.ref.startswith("registry"):
            out += ["## How to do this", src.read_text(encoding="utf-8").strip(), ""]
        # An agent that lists instructions gets only those; with none listed, all apply.
        wanted = [a.instructions for a in m.agents.values() if a.skill == name]
        limited = bool(wanted) and all(wanted)
        allowed = {r for lst in wanted for r in lst}
        for inst in m.instructions:
            if limited and inst.ref not in allowed:
                continue
            p = self._ctx.root / inst.ref
            if p.is_file() and p.resolve().is_relative_to(self._ctx.root.resolve()):
                out += [f"## Instructions ({inst.ref})", p.read_text(encoding="utf-8").strip(), ""]
        return "\n".join(out)

    def _write_claude_md(self) -> None:
        path = self._ctx.root / "CLAUDE.md"
        block = "\n".join(
            [
                BEGIN,
                "## ASAC skills",
                "",
                *[f"- `/{n}`: see .claude/skills/{n}/SKILL.md" for n in sorted(self._mounted)],
                END,
            ]
        )
        text = path.read_text(encoding="utf-8") if path.exists() else ""
        if BEGIN in text and END in text:
            head, rest = text.split(BEGIN, 1)
            _, tail = rest.split(END, 1)
            new = head + block + tail
        else:
            new = (text.rstrip() + "\n\n" if text.strip() else "") + block + "\n"
        path.write_text(new, encoding="utf-8")


def _yaml_str(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
