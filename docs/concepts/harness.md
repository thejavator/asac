# Harness

A **harness** is the agentic runtime that turns an LLM into an executable agent: agent loop, tool access, context management, permissions, user interface. Claude Code, GitHub Copilot and Cursor are harnesses; Bob is another. A bare LLM is not one.

`harness` is an **extension point**, not a fixed enum. The standard defines the interface; concrete harnesses are extensions published in the registry.

## Interface: `asac/harness-interface@2.0`

| Method | Contract |
|---|---|
| `mount(skill)` | Project an ASAC skill into the harness's native format (adapter) |
| `run(task, context)` | Execute a task: spec, memory, step inputs, required evidence |
| `tools(mcp_servers)` | Connect declared tools through the MCP gateway |
| `permissions(mode)` | Map `assist` / `delegate` onto the native approval model |
| `emit(event)` | Report logs, costs, artefacts and produced evidence to ASAC |
| `describe()` | Declare runtime capabilities: `headless`, `interactive`, `mcp`, `streaming` |
| `healthCheck()` | Verify availability and configuration |

!!! note "Breaking change in v0.3"
    `execute(skill, context)` was split into `mount` + `run` (a skill is mounted once per session, then tasks run). `getCapabilities()` was renamed `describe()` to avoid colliding with the `capability` resource.

## Skill adapters

| Harness | The skill becomes |
|---|---|
| `claude-code` | `.claude/skills/<skill>/SKILL.md` + `CLAUDE.md` |
| `copilot` | `.github/copilot-instructions.md` + prompt files |
| `cursor` | `.cursor/rules/<skill>.mdc` |
| `bob` | Bob rules + custom mode |
| `custom` | Adapter shipped by the extension |

This is what lets one developer use Cursor while the team uses Claude Code, on the same manifest.

## Declaring a harness

```yaml
harness:
  id: claude-code
  version: 2.0.0
  implements: asac/harness-interface@2.0
  runtime: { interactive: true, headless: true, mcp: true, streaming: true }
  adapter:
    skill_format: claude-skill
    target: .claude/skills/{skill}/SKILL.md
  permissions:
    assist: default       # approval on every action
    delegate: sandboxed   # autonomous, sandbox + OPA policy
```

## Built-in descriptors

Each known harness ships a declarative descriptor. `asac validate` reads it without starting the harness, and `describe()` must return the same values (checked by the conformance suite).

| Harness | interactive | headless | mcp | streaming |
|---|---|---|---|---|
| `claude-code` | yes | yes | yes | yes |
| `copilot` | yes | no | yes | no |
| `cursor` | yes | yes | yes | no |
| `bob` | yes | yes | yes | no |

## Implementation status

| Harness | Adapter |
|---|---|
| `claude-code` | `mount` and `run` in assist mode. `run` writes a brief under the state directory and hands the step to a person: the step resumes once its evidence is recorded (`asac evidence bootstrap`). Delegate is refused. |
| `codex` | `mount` plus `delegate`: the runner executes `codex exec -s workspace-write` |
| `cursor` | `mount` plus `delegate`: the runner executes `cursor-agent -p -f` |
| `bob`, `copilot` | `mount` and assist only. They have no known headless command, so a `delegate` step fails with a clear message (the descriptor of `bob` says headless, but no command is wired) |
| `fake` | Deterministic test double |

## The IDE-only rule

An IDE-only harness (for example Copilot) is valid **only for `mode: assist`**. A developer's personal choice can therefore never break a team's `delegate` step: `asac validate` detects it before anything runs.

## MCP servers (Claude Code)

A provider can declare how a harness reaches it as an MCP server. This is a layer-2 extension: the v0.4 resources are unchanged.

```yaml
providers:
  jira:
    source: registry.example.dev/providers/jira
    mcp:
      command: jira-mcp          # stdio server; or `url: https://...` for HTTP
      args: ["--stdio"]
      env:
        JIRA_TOKEN: ${vault.jira/token}   # references only (ASAC025)
```

For each step, `tools()` writes `.mcp.json` with only the servers listed in the step agent's `tools`, and `claude -p` gets `--strict-mcp-config --allowedTools mcp__<server>__*`. A step with no MCP tool gets no file and no extra flag. Secrets are written as `${ASAC_VAULT_<PATH>}` placeholders that Claude Code expands from the environment at run time (for example `ASAC_VAULT_JIRA_TOKEN`; pass the name in `runner_env` for a container). The value never reaches the file, the logs or the audit. Each step with MCP servers records a `tools.exposed` audit entry (server names only). An existing `.mcp.json` that asac did not write is never overwritten.
