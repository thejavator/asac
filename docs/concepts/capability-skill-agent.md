# Capability, skill, agent

| Brick | Role | Example | Layer |
|---|---|---|---|
| **capability** | WHAT the step must achieve | `implementation` | 1 |
| **skill** | HOW: a portable, versioned procedure | `java/implementation@3.0.0` | 1 (ref) + registry |
| **provider** | BRAIN: the LLM, or an external system | `claude-opus-5-5` | 1 + 2 |
| **harness** | BODY: the runtime that executes the loop | `claude-code`, `cursor` | 2 (via `var.*`) |
| **tools** | HANDS: systems reachable via MCP | `gitlab`, `jira` | 1 + 2 |
| **agent** | Composition of the bricks above | `dev` | 1 |

```yaml
capabilities:
  implementation: { inputs: [structured_spec], evidence: [tests_green] }
skills:
  java-impl:
    ref: registry.asac.dev/java/implementation@3.0.0
    fulfils: implementation
agents:
  dev: { skill: java-impl, provider: llm, harness: var.dev_harness, tools: [gitlab] }
```

## Independent evolution

- Change the LLM provider or harness → edit the agent or layer 2 only.
- Change the SDLC process → edit the pipeline and its capabilities only.

Skills are **not part of the harness**: they live in the registry, independent of any runtime. The harness receives them through an [adapter](harness.md#skill-adapters).
