# Roadmap and v0.5 backlog

## Specification

| Version | Status | Content |
|---|---|---|
| 0.2 | done | Three layers, capability/skill, `evidenceType`, `mode` |
| 0.3 | done | Harness as runtime, adapters, execution model |
| **0.4** | **frozen** | Agent governance: `knowledge`, `instruction`, `budget`, `hook`, `autonomy`, `escalation`, `specLevel` |
| 0.5 | planned | See backlog below |

## Reference implementation (no dates promised)

1. Parser and `asac validate` (three layers, harness/mode compatibility): **done**.
2. `plan` / `apply` engine, local state backend: **done**.
3. Headless runner (Docker) and Claude Code delegation: **done**. MCP servers per step (`.mcp.json`, allow list, audit): **done** for Claude Code. MCP gateway: not started.
4. Portal (SPA, API, OIDC, Decision Room, administration, pipeline editor, forges, tracker and wiki, deliverables and costs): **done**. DORA and token metrics: not started.
5. Public registry, provider SDKs: not started. Other headless harnesses: not started. Parallel steps: the code exists (`parallel`, 1 to 8) but no real test covers it; not in 0.1.
5b. Worker that consumes the job queue, and `mode: delegate` through the Docker runner: planned for 0.1.x (SCOPE_V1, lot 5). Multi-agent orchestration (frameworks, `critic`, `routing`): deferred, see the backlog below.
6. Multi-team (multi-project portal): **done**. Agent identity and audit export aids: partly done (CSV export).

The detailed task list is `TACHES.md` at the repository root.

## Next: where the request comes from

Today the request an agent works on is a file in the repository (`REQUEST.md` in the example),
read by the spec skill. A run started from the portal or the CLI cannot say what to build. The
main flow should instead start from the tool the product owner already uses. In order:

| # | Item | What exists | What is missing |
|---|---|---|---|
| 1 | **Run from a ticket** (main flow). The product owner creates a ticket in Jira, Monday or another tracker; the ticket starts the run, and its text is the request. | Webhooks for Jira, GitHub and GitLab start a run with a stable id (`run_<pipeline>_<key>`), HMAC check, label and type filters. Tracker adapters read an issue (Jira, GitHub, GitLab). | The ticket's title and description never reach the agent: the webhook keeps only the key. Monday (and other trackers) have no adapter. Status is not written back to the ticket. The daemon returns HTTP 500 when the project is not a git repository. |
| 2 | **Request typed at launch.** A field in the portal's launch form (and `asac apply --request`), for runs that do not start from a ticket. | The portal can start a run (`POST /runs`, pipeline only). | A request field; writing it into the run's worktree where the spec skill reads it; the audit records who wrote it and its digest. |
| 3 | **Conversation with the agent.** A chat in the run page to clarify the request before or during a step. | Rejection with a reason relaunches the agent with that reason (under autorun), which is a one-shot form of it. | A thread per run and step; each message appended to the agent's feedback and to the audit; a design for when a message relaunches the agent and when it waits for a gate. |

Rule for all three: the request is an input of the run, like the commit it starts from. It is
recorded once, with its source (ticket key, portal user, chat author) and a digest, so a gate
approves work against a request that cannot change behind it.

## v0.5 backlog

| Item | Reason deferred | Destination |
|---|---|---|
| Multi-agent orchestration (agents that call or hand off to other agents, a planner that delegates; frameworks such as LangGraph, CrewAI, AutoGen) | ASAC orchestrates the steps of the cycle and their guarantees; each agent organises its own work (Claude Code and Codex do it internally). A framework would move the process into Python code and bypass the harnesses. Revisit only if a need appears that steps and gates cannot express | Engine, if needed |
| Durable workflow engine (Temporal, Prefect, Hatchet) | Only if runs must survive worker crashes over long timers, many hosts or many concurrent runs; SQLite state, resume and `SKIP LOCKED` cover the small case | Engine |
| `routing` (multi-model) | Routing by capability, sensitivity and cost with fallback; design undecided | Layer 2 |
| `critic` pattern | "QA ≠ dev" exists as policy; the declared pattern does not. The most aligned with ASAC's promise: a second agent, ideally from another provider, that cannot approve its own work | Step |
| `integration_green`, `e2e_green` | Extensions of `tests_green`; just evidence types | Spec or module |
| `canary_healthy`, `post_deploy_verified` | Needs a progressive-delivery model | Release step |
| `monitor.signal` event | Remediation from production; Monitor → Plan loop | Spec |
| `knowledge` index provider | Semantic/hybrid RAG, graph; only OKF and MCP in v0.4 | Provider |
| `scope.paths` | Feasible in Rego and sandbox today; declarative comfort | Step |
| `arch_conform` | Module-provided evidence (ArchUnit, dependency-cruiser) | Golden Path module |
| Golden Paths | Assembly of existing primitives | Template catalogue |
