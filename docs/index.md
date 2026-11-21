# ASAC — Agentic SDLC as Code

> **Declare your software delivery. Let agents execute it.**

ASAC is an open, declarative framework for describing a software delivery lifecycle (SDLC) as code and running it with AI agents, under explicit governance.

| Domain | Declarative tool | What you declare |
|---|---|---|
| Infrastructure | Terraform | Resources |
| Containers | Kubernetes | Desired state |
| Software delivery | **ASAC** | Capabilities, agents, pipelines, gates, evidence |

!!! warning "Status"
    ASAC is a **language specification (v0.4, frozen)**. **Version 0.1 supports one path, end to end:** `validate`, `apply`, the Claude Code harness, hooks and Rego checks, a human gate bound to a commit, `approve`, `evidence verify`, `audit`, `clean`, plus `doctor` and the step `loop`. Each run works in its own git worktree, and with the sandbox on (`srt`) the agent cannot rewrite the rules, delete the audit, read your keys or reach other hosts. **Everything else in this repository exists but is not supported in 0.1:** the web portal and daemon, the forge adapters, the Docker and Kubernetes runners, the other harnesses (they only mount files), MCP and Postgres. Their tests use fakes, never the real system. The registry is not implemented. See [Roadmap](project/roadmap.md). See [Versioning](project/versioning.md) and the [Roadmap](project/roadmap.md).

## The problem

Teams adopt AI coding tools one by one, with no shared conventions, no governance, and no way to verify what agents actually did.

| Without ASAC | With ASAC |
|---|---|
| Each developer has their own AI workflow | `asac.yaml` is the single source of truth for the team's SDLC |
| Nobody knows an agent touched the code | Every agent action produces **evidence** |
| "The agent wrote it" is not an audit answer | The evidence chain records who approved what, and when |
| Switching tools breaks everything | Change `var.dev_harness`; the pipeline is unchanged |
| "QA agent ≠ dev agent" is a convention | It is a policy, enforced by OPA |

## A minimal taste

```yaml
capabilities:
  implementation:
    inputs: [structured_spec]
    evidence: [tests_green]
agents:
  dev:
    skill: java-impl
    provider: llm
    harness: var.dev_harness   # resolved in layer 2
pipelines:
  feature:
    steps:
      development:
        capability: implementation
        agent: dev
        mode: delegate
        gate: { type: human, role: product_owner }
```

## Design principles

1. **Separate what from how.** A *capability* says what must be achieved; a *skill* says how.
2. **Three layers, three audiences.** Manifest, runtime values, policies.
3. **Nothing without evidence.** A step starts only when the evidence it requires exists.
4. **Plan before apply.** Preview what agents will do before they do it.
5. **Assist before delegate.** Never delegate what you have not first proven you can assist.
6. **Open standard.** The spec is open; anyone may implement a compatible runtime.

## Where to go next

- New here? Read [Concepts](concepts/index.md), then the [Quick start](getting-started/quickstart.md).
- Want the full picture of a project? See the [complete example](reference/example.md).
- Evaluating for your organisation? See [Agent governance](concepts/governance.md) and [Maturity levels](guides/maturity.md).
