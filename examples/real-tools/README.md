# Example: ASAC with the AI tools on your machine

A tiny Python task list (`app/`) and a two-step pipeline (`requirements` → `development`),
each step ending in a human gate. One variable, `tool`, selects the AI tool.

| Tool | `TOOL` value | Files ASAC mounts | Launched by |
|---|---|---|---|
| Claude Code | `claude-code` | `.claude/skills/<skill>/SKILL.md`, `CLAUDE.md` | `claude -p` |
| Codex | `codex` | `AGENTS.md` (managed block) | `codex exec` |
| Cursor | `cursor` | `.cursor/rules/asac-<skill>.mdc` | `cursor-agent -p` |
| IBM Bob | `bob` | `.bob/skills/<skill>/SKILL.md` | opens `bobide` on the folder |
| Antigravity | `antigravity` | `.agent/skills/<skill>/SKILL.md` | opens the app on the folder |

Follow [RUNBOOK.md](RUNBOOK.md): it gives every command, in order, to copy and run. You work in a
scratch copy, launch the tool yourself on one step at a time, then record evidence and approve.
The post-step hook `tests-green` runs the project's real unit tests, so a step cannot finish
while they fail.

## What is verified, and what is not

- Automated (`tests/test_real_tools_example.py`): validation, mounting for all five tools, hand-off, and the
  hook blocking when the real tests fail. No tool is launched and no network is used.
- Not verified by the tests: that each tool picks up the mounted file. The paths follow each tool's documented
  project conventions. Step 2 of the runbook checks it; Bob and Antigravity are GUI apps, so open the folder and
  confirm the skill or rule is listed.
- Assist mode only: ASAC writes a brief and a person (or the tool you launch) does the work. Delegate mode
  (a container runs the tool) exists for Claude Code, Codex and Cursor; it is only tested with fakes.
