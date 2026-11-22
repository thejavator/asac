# Agent governance (v0.4)

Spec v0.4 adds four primitives and two step attributes. They do not change the definition of a harness: they describe what the harness is *given* and the limits it acts within. CLI commands (`asac kill`, …) are tools, not primitives.

| Primitive | Meaning | Layer |
|---|---|---|
| `knowledge` | What the agent knows: provenance, `trust_tier`, `owner`, `stale_after`. Providers in v0.4: OKF files, MCP server | 1 (structure) + 2 (access) |
| `instruction` | Versioned project rules: conventions, "never X", output contracts, escalation rules. Projected by the adapter to `CLAUDE.md`, `AGENTS.md` or `.cursor/rules` | 1 |
| `budget` | Ceilings per run and per step: tokens, cost, duration, iterations. Overrun = stop and escalate | 1 (ceilings) + 3 (enforcement) |
| `hook` | Deterministic checks before/after a tool call or step: secret scan, dependency check, eval suite | 1 (ref) + 3 (rules) |

```yaml
knowledge:
  project-okf: { provider: okf, path: .asac/knowledge, stale_after: 90d, trust_tier: reviewed }
instructions:
  - ref: .asac/instructions/security.md
budgets:
  per_run:  { tokens: 2000000, cost_usd: 15, wall_clock: 2h }
  per_step: { iterations: 5 }
hooks:
  pre_tool:  [secret-scan]
  post_step: [deps-verify, eval-suite]
pipelines:
  feature:
    specLevel: 3   # 1 story · 2 versioned spec · 3 executable spec
```

`asac validate` warns (`ASAC026`) when the declared level is not backed: level 2 needs a gated step whose evidence a later step requires, and level 3 also needs a hook or step policy that checks the spec. It never blocks.

## Hooks

A hook is a deterministic check, with no LLM, run at a fixed point: `pre_tool` (before a tool call) or `post_step` (after a step). It answers pass or fail through its exit code (`0` passes, anything else fails). A hook is defined either locally or from a registry, exactly one of the two:

```yaml
hooks:
  definitions:
    secret-scan: { run: .asac/hooks/secret-scan.sh, on_fail: block }
    deps-verify: { ref: registry.example.dev/hooks/deps-verify@1.2.0#sha256:<digest> }
  pre_tool:  [secret-scan]
  post_step: [deps-verify]
```

`on_fail` is `block` (default) or `warn`. A local hook runs only when its path is inside the repository and listed in the manifest; it is never discovered. A registry hook requires a verified digest.

### Hooks for one step

`hooks.pre_tool` and `hooks.post_step` run on **every** step. A check that only makes sense for
one step is attached to that step instead. The script is still declared once, in
`hooks.definitions`; the step only says which ones it runs:

```yaml
hooks:
  definitions:
    no-secrets:  { run: .asac/hooks/no-secrets.sh }
    step-scope:  { run: .asac/hooks/step-scope.sh }
    tests-green: { run: .asac/hooks/tests-green.sh }
  pre_tool: [no-secrets]                 # every step

pipelines:
  feature:
    steps:
      requirements:
        hooks: { pre_tool: [step-scope], post_step: [step-scope] }
      development:
        hooks: { post_step: [tests-green] }   # never runs on requirements
```

A step runs the global hooks first, then its own, in the order written. A hook listed in both runs
once, at its global place. `asac validate` refuses a step hook that is not declared (`ASAC012`),
and a manifest that writes the same key twice (YAML would otherwise keep only the last one, and
silently drop a check). In the audit, each result says when it ran: `pre_tool <hook>` or
`post_step <hook>`.

## Autonomy

A step attribute, orthogonal to `mode`:

```yaml
development:
  mode: delegate        # WHERE it runs
  autonomy: review      # HOW MUCH freedom
  escalation: { outside_scope: human }
```

| `autonomy` | Behaviour | Typical maturity |
|---|---|---|
| `readonly` | Reads and proposes; no write, no action on external systems | L0–L1 |
| `review` | Acts within scope; every output passes a human gate before taking effect | L2–L3 |
| `autonomous` | Acts without a human gate within scope; escalates automatically outside it | L4, proven capabilities |

!!! warning "Autonomy doctrine"
    `autonomous` should not be declared without a **written doctrine**, validated by security and legal, then translated into `.rego`. This is organisational guidance; the specification does not enforce it mechanically.

## New evidence and policies

| Name | Kind | Risk covered |
|---|---|---|
| `deps_verified` | evidence | Non-existent or hallucinated dependencies (slopsquatting): deterministic check against allowed registries |
| `no_regression` | policy | Security degradation between iterations of one step: score must not decrease, otherwise block |
| `hills_defined`, `prfaq_approved` | evidence | `discovery` pipeline: the need is framed before delivery |
| `tda_signed` | evidence | Architecture review before production |
| `outcome_reviewed` | evidence | Outcome review (pivot or scale); Monitor → Plan feedback loop |

## Skill supply chain

A skill reference can be pinned by digest and require a valid signature:

```yaml
ref: registry.asac.dev/core/quality-assurance@2.5.0#sha256:<digest>
```

A silently modified skill could impose dependencies or behaviours; pinning makes modification detectable.

## Data residency

Declared in layer 2 (`asac.vars.yaml`), for example `data_residency: eu`, because it is a value that differs per environment.

## Implementation status

How the reference implementation enforces each primitive (the specification leaves the mechanism open):

| Primitive | Behaviour |
|---|---|
| Budgets | After every harness run, tokens and cost reported by the harness are added up for the run. Over `per_run` → the step and the run are `blocked`, exit 3. `per_step.iterations` is checked against the reported iterations. |
| `autonomy: readonly` | The harness receives permission `readonly` instead of the step mode. |
| `autonomy: review` | The step's own gate (if any) applies; `review` does not add a gate by itself. |
| `autonomy: autonomous` | Blocked unless at least one `instructions` entry is declared (the doctrine). |
| `escalation` | A harness-reported reason mapped to `human` opens a wait (exit 2); an unmapped reason blocks (exit 3). |
| Policies | A gate `policy` (.rego) is evaluated through the `PolicyEngine` port (OPA, offline) before the gate opens: `block` → exit 3, `escalate` → exit 2. `no_regression` is built in (score must not fall). |
| `asac kill <run-id>` | Sets the run to `killed`; checked before every step, never resumable. |
| `asac learn <run-id>` | Writes `.asac/proposals/<run-id>.md` from failures and blocks. Never applied. |
| `asac logs --json` | One OpenTelemetry-shaped span per audit record. |
