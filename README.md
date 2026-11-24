# ASAC — Agentic SDLC as Code

> **Declare your software delivery. Let agents execute it.**

ASAC is an open, declarative framework for describing a software delivery lifecycle as code (capabilities, agents, pipelines, gates, evidence) and running it with AI agents under explicit governance. Terraform is to infrastructure and Kubernetes to containers what ASAC aims to be to the SDLC.

> **Status: specification v0.4 (frozen), reference implementation 0.1.** **Version 0.1 supports one path, end to end:** `init`, `validate`, `plan`, `apply`, `run`, the Claude Code harness, hooks and Rego checks, `submit` for work done by hand, a human gate bound to a commit, `approve`, `evidence verify`, `audit`, `clean`, plus `doctor`, `vars`, `learn` and the step `loop`. Each run works in its own git worktree, and with the sandbox on (`srt`) the agent cannot rewrite the rules, delete the audit, read your keys or reach other hosts. **Not supported in 0.1:** the web portal and daemon, the forge adapters, the Kubernetes runner, the other harnesses (they only mount files), MCP and Postgres. Their tests use fakes, never the real system. The registry is not implemented. See [SCOPE_V1.md](SCOPE_V1.md) and [asac-specs-v1.md](asac-specs-v1.md).

## Three layers

| Layer | File | Declares |
|---|---|---|
| 1 | `asac.yaml` | What: capabilities, agents, pipelines, evidence, gates |
| 2 | `asac.vars.yaml` | Values: URLs, secret references, harness choices |
| 3 | `.asac/policies/*.rego` | Rules, enforced by OPA |

## Documentation

```bash
pip install zensical
zensical serve        # http://127.0.0.1:8000
```

Start with `docs/index.md`, then Concepts and the Quick start.

## Example

[`examples/payments-service`](examples/payments-service) is a complete three-layer project. CI parses the YAML and runs `opa test` on the policy.

## Versioning

Language spec and reference implementation are versioned separately. See [docs/project/versioning.md](docs/project/versioning.md).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) and the [Code of Conduct](CODE_OF_CONDUCT.md). Report vulnerabilities as described in [SECURITY.md](SECURITY.md).

## License

Apache License 2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
