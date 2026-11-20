# Six pillars mapping

*Harness engineering* describes what to build around a model to get a reliable agent: **Instructions, Knowledge, Skills, Tools, Orchestration, Control**. This page shows where each pillar lives in ASAC.

> Agent = Model + Harness

| Pillar | Content | ASAC primitive | Since |
|---|---|---|---|
| 1. Instructions | System prompts, `CLAUDE.md`/`AGENTS.md`, output contracts, "never X", escalation rules | `instruction` (+ harness adapter) | v0.4 |
| 2. Knowledge | Structured docs, RAG, graph, memory, freshness, context budget | `knowledge` | v0.4 |
| 3. Skills | Reusable, versioned procedures | `skill` + registry | v0.2; digest and signature v0.4 |
| 4. Tools | System access (MCP), sandbox, human approval as a tool | `provider` + MCP gateway + `execution.sandbox` | v0.2–v0.3 |
| 5. Orchestration | Pipeline, sub-agents, review, iteration limits | `pipeline`, `step`, `agent`, `budget.per_step` | v0.2; budgets v0.4 |
| 6. Control | Hooks, gates, budgets, kill-switch, audit, evals | `gate`, `evidenceType`, `.rego`, `hook`, `budget`, `autonomy` | gates v0.2; rest v0.4 |

## Reading an agent through the six pillars

An agent's description answers six questions:

| Question | Pillar |
|---|---|
| Which rules does it follow? | 1 |
| What can it consult, and is it up to date? | 2 |
| Which procedure does it apply? | 3 |
| Which systems can it access? | 4 |
| Who reviews it, how many iterations? | 5 |
| What stops or escalates it? | 6 |

## Pillars across the feature pipeline

Cells are illustrative, not obligations.

| Step | Instructions | Knowledge | Skills | Tools | Orchestration | Control |
|---|---|---|---|---|---|---|
| Discovery | Hills / PR-FAQ format | User research | core/discovery | Wiki, analytics | PO + BA | `hills_defined`, `prfaq_approved` |
| Requirements | Spec format | Domain, ADRs | core/specification | Issue tracker | BA → PO | `spec_reviewed` |
| Development | Conventions, "never X" | Code, project OKF | java/implementation | Git, build | dev; independent review | `tests_green`, `deps_verified`, `no_regression`, budget |
| Verification | Acceptance criteria | Spec, bug history | core/quality-assurance | Sonar, CI | qa ≠ dev | `sast_clean`, `coverage_passed`, `qa_approved` |
| Release | Deployment rules | Runbooks | core/release | CD, registry | devops | `tda_signed`, `deployed` |
| Operate | Autonomy doctrine | Past incidents | core/incident | Observability | loop back to Plan | `outcome_reviewed`, kill-switch |
