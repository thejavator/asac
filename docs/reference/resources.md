# Resource types

Nine core primitives, plus four added in v0.4.

| Resource | Meaning | Layer |
|---|---|---|
| `capability` | WHAT a step must achieve; declares inputs, outputs, expected evidence | 1 |
| `evidenceType` | A named proof; extensible by registry modules | 1 |
| `skill` | HOW: versioned registry module implementing a capability (`fulfils`) | 1 (ref) + registry |
| `provider` | Integration to an external system or LLM; config via `var.*` | 1 + 2 |
| `agent` | skill + provider + harness + tools | 1 (+ 2 for harness) |
| `pipeline` | Ordered flow: trigger, steps (`dependsOn`, `requiresEvidence`, `producesEvidence`), gates | 1 |
| `gate` | Control point: `human` / `quality` / `automated`, role or policy | 1 (core) + 3 (rules) |
| `variable` | Interface between layers 1 and 2 | 1 + 2 |
| `harness` | Extension point: the agentic runtime | interface in standard, values in extensions |
| `knowledge` *(v0.4)* | Sources with provenance and freshness | 1 + 2 |
| `instruction` *(v0.4)* | Versioned project rules | 1 |
| `budget` *(v0.4)* | Per-run and per-step ceilings | 1 + 3 |
| `hook` *(v0.4)* | Deterministic pre/post checks | 1 + 3 |

## Step attributes

| Attribute | Values | Since |
|---|---|---|
| `capability`, `agent`, `dependsOn` | references | 0.2 |
| `mode` | `assist`, `delegate` | 0.2 |
| `requiresEvidence`, `producesEvidence` | lists of evidence types | 0.2 |
| `gate` | `{type, role \| policy, timeout}` | 0.2 |
| `execution` | `{runner, sandbox, fallback}` | 0.3 |
| `autonomy` | `readonly`, `review`, `autonomous` | 0.4 |
| `escalation` | e.g. `{outside_scope: human}` | 0.4 |
| `policies` | e.g. `[no_regression]` | 0.4 |

Pipeline attributes: `description`, `timeout`, `trigger`, `steps`, and (v0.4) `specLevel` 1–3.

## Cross-reference checks

`asac validate` also checks that references and durations are usable, so a limit never fails silently at run time:

- `ASAC021`: an agent lists an `instructions` entry that is not declared at the top level.
- `ASAC022`: an agent lists a `knowledge` entry that is not declared at the top level.
- `ASAC023`: a duration (`budgets.per_run.wall_clock`, `pipeline.timeout`, `gate.timeout`) does not parse. Use `30m`, `24h` or `2d`.
- `ASAC024`: a provider `mcp` block needs exactly one of `command` (stdio) or `url` (`https://`).
- `ASAC025`: a value in `providers.<name>.mcp.env` is not a `${vault...}` reference. Secrets are never written in the manifest.
- `ASAC026` (warning): `specLevel` is not backed. Level 2 needs a gated step whose evidence a later step requires. Level 3 also needs a hook or a step policy that checks the spec. Level 1 asks for nothing.

At run time, `budgets.per_run.wall_clock` and `pipeline.timeout` are measured from the creation of the run and block it (exit code 3) when exceeded.
