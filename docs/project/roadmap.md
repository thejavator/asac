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
5. Public registry, provider SDKs: not started. Other headless harnesses, parallel steps: not started.
6. Multi-team (multi-project portal): **done**. Agent identity and audit export aids: partly done (CSV export).

The detailed task list is `TACHES.md` at the repository root.

## v0.5 backlog

| Item | Reason deferred | Destination |
|---|---|---|
| `routing` (multi-model) | Routing by capability, sensitivity and cost with fallback; design undecided | Layer 2 |
| `critic` pattern | "QA ≠ dev" exists as policy; the declared pattern does not | Step |
| `integration_green`, `e2e_green` | Extensions of `tests_green`; just evidence types | Spec or module |
| `canary_healthy`, `post_deploy_verified` | Needs a progressive-delivery model | Release step |
| `monitor.signal` event | Remediation from production; Monitor → Plan loop | Spec |
| `knowledge` index provider | Semantic/hybrid RAG, graph; only OKF and MCP in v0.4 | Provider |
| `scope.paths` | Feasible in Rego and sandbox today; declarative comfort | Step |
| `arch_conform` | Module-provided evidence (ArchUnit, dependency-cruiser) | Golden Path module |
| Golden Paths | Assembly of existing primitives | Template catalogue |
