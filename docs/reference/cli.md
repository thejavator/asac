# CLI reference

!!! info "Implementation status"
    Supported in 0.1: `doctor`, `validate`, `apply [--resume]`, `status`, `gates`, `approve`, `evidence show|verify`, `logs`, `audit`, `kill`, `clean`. Present but not supported in 0.1:  `version`, `init`, `validate`, `vars check|diff`, `plan`, `apply [--resume] [--watch]`, `run`, `status`, `gates`, `approve`, `evidence show|verify|bootstrap`, `logs [--json]`, `audit`, `kill`, `learn`. Harnesses: `claude-code` (assist mode hands off; delegate mode runs `claude -p` in a runner. It writes `.claude/skills/<skill>/SKILL.md` and a managed block in `CLAUDE.md`, then hands the step to a person) and `fake` (tests). `codex`, `cursor`, `bob`, `antigravity` and `copilot` are assist adapters that mount the skill where the tool reads project instructions (`AGENTS.md`, `.cursor/rules`, `.bob/skills`, `.agent/skills`, `.github/instructions`) and hand off; see `examples/real-tools`. Local hooks (`run:`) run after each step. Also implemented: `portal` and `daemon` (see [Portal and daemon](portal.md)). Delegate execution runs in a Docker runner (Claude Code only). MCP wiring works for `claude-code` (see [Harness](../concepts/harness.md)). Not yet implemented: `ref:` hooks, registry and provider commands. The table below is the target contract.

| Command | Description |
|---|---|
| **Setup** | |
| `asac init` | Generate a minimal `asac.yaml` with stack detection, plus `asac.vars.yaml.example` and `.asac/policies/`. `--mode observe`, `--template <name>` |
| `asac doctor` | Check git, opa, node (>= 22.12), srt and claude, and that the project is a clean git repository. Says how to fix each failure; exit 1 if a required one fails |
| `asac clean <run>` | Remove a run's worktree and keep its branch `asac/<run>`. Refused while the run is not finished unless `--force` |
| `asac validate` | Validate the three layers: manifest syntax, `var.*` resolution, capability/skill consistency, Rego policies, harness/mode compatibility |
| `asac provider install` | Install the declared providers and harness extensions |
| **Vars (layer 2)** | |
| `asac vars check` | Check that every `var.*` is resolved |
| `asac vars diff` | Show missing or unused variables |
| **Execution** | |
| `asac plan` | Show what agents will do (steps, gates, estimated cost) without executing. `--dry-run` simulates effects of a step |
| `asac apply` | Execute a pipeline; verify required evidence before each step; block on gates |
| `asac run <step>` | Run a single step |
| **Evidence & gates** | |
| `asac evidence show` | Evidence status for a run |
| `asac evidence verify` | Check a step's required evidence |
| `asac evidence bootstrap` | Produce baseline evidence for existing code (marked as bootstrapped) |
| `asac gates` | List pending human gates |
| `asac approve <gate-id>` | Approve a gate from the CLI. Rejecting needs `--comment`. A gate with a `role` is refused unless the approver holds it |
| `asac apply --watch [--poll <s>]` | Stay in the foreground and continue after each decision until the run ends |
| `asac apply --resume <run-id> --reopen` | Reopen the rejected gate(s) of a failed run so they can be decided again. The rejection stays in the audit as `gate.rejected`; the reopening is recorded as `gate.reopened` |
| **Monitoring & audit** | |
| `asac status` | Running pipelines and pending gates |
| `asac logs <run-id>` | Logs per step and agent, with OpenTelemetry spans |
| `asac audit` | Full audit log; `--format csv` for export |
| **Governance (v0.4, tools not primitives)** | |
| `asac kill <run-id>` | Stop a run immediately and revoke its access (kill-switch) |
| `asac learn <run-id>` | Propose a Rego rule, instruction or skill update from failed gates |
| **Registry & portal** | |
| `asac registry search` | Search skills, providers, modules |
| `asac skill publish` | Publish a skill; embedded evals run first |
| `asac portal` | Start the local governance portal (PO, QA, manager) |

## Exit codes

| Code | Meaning |
|---|---|
| `0` | Completed |
| `1` | Error |
| `2` | Waiting for a human gate. `asac approve` and `asac evidence bootstrap` continue the run themselves (`--no-resume` to opt out); `asac apply --watch` keeps following it; `asac apply --resume <run-id>` resumes after a crash or a block |
| `3` | Blocked by a policy or a budget |
