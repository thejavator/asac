"""Assist adapters for tools that read project files: Codex, Cursor, Bob, Antigravity, Copilot.

``mount`` writes the skill where the tool looks for project instructions; ``run`` writes a
task brief and hands the work to the person (assist mode), like the Claude Code adapter.
The target paths follow each tool's documented project conventions; they have been
checked against the tools only where the example README says so.
"""

from __future__ import annotations

from asac.adapters.base import HarnessError, safe_name
from asac.adapters.claude_code import BEGIN, END, ClaudeCodeHarness


class _FileMount(ClaudeCodeHarness):
    def mounted_path(self, skill: str) -> str:
        return self._target(skill)

    def _target(self, skill: str) -> str:
        raise NotImplementedError

    def _body(self, name: str) -> str:
        return self._skill_md(name)

    def mount(self, skill: str) -> None:
        if skill not in self._ctx.manifest.skills:
            raise HarnessError(f"unknown skill '{skill}'")
        name = safe_name(skill)
        target = self._ctx.workdir / self._target(name)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self._body(name), encoding="utf-8")
        if name not in self._mounted:
            self._mounted.append(name)
        self._index()

    def command(self, prompt: str, readonly: bool) -> list[str] | None:
        return None

    def _index(self) -> None:
        """Optional index file for tools that read one root file."""


class _SkillDirMount(_FileMount):
    skill_root = ""

    def _target(self, skill: str) -> str:
        return f"{self.skill_root}/{skill}/SKILL.md"


class BobHarness(_SkillDirMount):
    harness_id, tool_name, launch_hint = "bob", "IBM Bob", "bobide ."
    skill_root = ".bob/skills"


class AntigravityHarness(_SkillDirMount):
    harness_id, tool_name, launch_hint = "antigravity", "Antigravity", "open -a Antigravity ."
    skill_root = ".agent/skills"


class CursorHarness(_FileMount):
    harness_id, tool_name, launch_hint = "cursor", "Cursor", "cursor ."

    def command(self, prompt: str, readonly: bool) -> list[str] | None:
        return ["cursor-agent", "-p", *([] if readonly else ["-f"]), prompt]

    def _target(self, skill: str) -> str:
        return f".cursor/rules/asac-{skill}.mdc"

    def _body(self, name: str) -> str:
        text = self._skill_md(name)
        _, _, rest = text.split("---", 2)  # drop the SKILL.md frontmatter
        desc = " ".join(f"ASAC skill {name}".split())
        head = f"---\ndescription: {desc}\nalwaysApply: false\n---\n"
        return head + rest.lstrip("\n")


class CopilotHarness(_FileMount):
    harness_id, tool_name, launch_hint = "copilot", "GitHub Copilot", "code ."

    def _target(self, skill: str) -> str:
        return f".github/instructions/asac-{skill}.instructions.md"

    def _body(self, name: str) -> str:
        _, _, rest = self._skill_md(name).split("---", 2)
        return '---\napplyTo: "**"\n---\n' + rest.lstrip("\n")


class CodexHarness(_FileMount):
    """Codex reads ``AGENTS.md``: every mounted skill is one managed section of it."""

    harness_id, tool_name, launch_hint = "codex", "Codex", "codex"

    def command(self, prompt: str, readonly: bool) -> list[str] | None:
        sandbox = "read-only" if readonly else "workspace-write"
        return [
            "codex", "exec", "-s", sandbox, "--skip-git-repo-check",
            "-C", str(self._ctx.workdir), prompt,
        ]  # fmt: skip

    def mounted_path(self, skill: str) -> str:
        return f"AGENTS.md (section 'ASAC skill: {skill}')"

    def _target(self, skill: str) -> str:
        return f".asac-mount/codex/{skill}.md"  # source of the section; AGENTS.md is the index

    def _body(self, name: str) -> str:
        _, _, rest = self._skill_md(name).split("---", 2)
        return rest.lstrip("\n")

    def _index(self) -> None:
        sections = []
        for n in sorted(self._mounted):
            body = (self._ctx.workdir / self._target(n)).read_text(encoding="utf-8")
            sections.append(f"## ASAC skill: {n}\n\n" + body.replace("\n# ", "\n### ", 1))
        block = "\n".join([BEGIN, *sections, END])
        path = self._ctx.workdir / "AGENTS.md"
        text = path.read_text(encoding="utf-8") if path.exists() else ""
        if BEGIN in text and END in text:
            head, rest = text.split(BEGIN, 1)
            _, tail = rest.split(END, 1)
            new = head + block + tail
        else:
            new = (text.rstrip() + "\n\n" if text.strip() else "") + block + "\n"
        path.write_text(new, encoding="utf-8")
