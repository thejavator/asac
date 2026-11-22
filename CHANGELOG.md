# Changelog

See [docs/project/changelog.md](docs/project/changelog.md) for the specification changelog.

## Unreleased

- Hooks per step: `steps.<id>.hooks.pre_tool` and `.post_step` list the declared hooks a step runs,
  after the global ones. A step no longer has to guard its script by step name.
- `asac validate` refuses a duplicated key in a manifest instead of keeping only the last one.
- The audit records when a hook ran (`pre_tool` or `post_step`), and the portal shows it.
- A run started from the portal now gets its own worktree, like one started by the CLI.
- `asac portal --local` for a developer, `asac portal --project ID=PATH` for a shared portal.

## 0.1.0 (2026-11-21): first supported path

Version 0.1 supports one path end to end: `doctor`, `validate`, `apply`, `approve`, `gates`,
`status`, `logs`, `audit`, `evidence`, `clean`, `kill`, with Claude Code as the only tool.

- Each run works in its own git worktree on branch `asac/<run>`; the main checkout is never
  written. ASAC makes the commit of each step and the human gate is bound to that commit.
- Hooks run in the worktree but are read from the main checkout; a step that changes a rule
  (`asac.yaml`, `asac.vars.yaml`, `.asac/`) is blocked and audited (`integrity.violated`).
- `step.loop`: retry the agent with the reason its work was rejected, with a mandatory cap.
- OS sandbox (`srt`, `ASAC_SANDBOX=1`): write only in the worktree, no secrets, listed hosts only.
- Real cost from `claude -p --output-format json`; an unknown cost blocks a cost budget.
- `asac doctor` and `asac clean`.

Not supported in 0.1, present in the repository: the web portal and daemon, the forge adapters,
the Docker and Kubernetes runners, the other harnesses, MCP, Postgres. The registry is not
implemented. Known limits: the sandbox reaches the model API only; approval identity is declared
on the command line; macOS only.

## Repository

- Initial public release of the v0.4 specification documentation, example project and tooling.
