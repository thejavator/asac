# Execution model

The step's **`mode`** determines where it runs. The chosen harness must declare the matching runtime, otherwise `asac validate` fails.

| `mode` | Where | Runtime required | Triggered by |
|---|---|---|---|
| `assist` | The persona's machine (IDE / terminal) | `interactive: true` | *Push-to-harness*: ASAC notifies, the developer opens the task |
| `delegate` | An **ASAC Runner** (server / CI, isolated container) | `headless: true` | The ASAC **Daemon**, on an event (webhook, approved gate) |

`mode` is set on the **step**, never on the agent. The same agent can assist in one pipeline and be delegated in another.

## Optional explicit execution

```yaml
steps:
  development:
    capability: implementation
    agent: dev
    mode: delegate
    execution:
      runner: var.runner_pool   # k8s, gitlab-runner…
      sandbox: container
      fallback: assist          # if no runner is available
```

## Validation output

```text
$ asac validate
✓ step requirements  ba       assist    copilot      interactive
✓ step development   dev      delegate  claude-code  headless
✗ step verification  qa       delegate  cursor
    harness 'cursor' does not declare headless: true
    → use mode: assist, or override qa_harness in vars
```

## `mode` vs `autonomy`

`mode` answers **where** a step runs. [`autonomy`](governance.md#autonomy) (v0.4) answers **how much freedom** the agent has. They are orthogonal.

## Retrying a failed step

A step whose harness or runner fails is retried in place when `retries` is set in the vars file (or `ASAC_RETRIES` in the environment). The value is the number of extra attempts, from 0 (default) to 5. Each retry writes a `step.retry` audit entry. Blocks, gates and budget stops are never retried, only failures. After the last attempt the step fails as before and the run stays resumable with `asac apply --resume`.

## Running independent steps in parallel

Steps are grouped in waves: a step starts in the first wave after all the steps it needs. By default the engine runs one step at a time. Set `parallel` in the vars file (or `ASAC_PARALLEL` in the environment) to a number from 1 to 8 to run the steps of one wave together. Any other value means 1. State writes are serialised, a gate or a block in one step does not stop its siblings from finishing, and the first outcome in plan order decides how the run stops. Budgets, audit and evidence work as in sequential mode.
