# ASAC — Agentic SDLC as Code

> **Declare your software delivery. Let agents execute it.**

ASAC is an open, declarative framework for describing a software delivery lifecycle as code (capabilities, agents, pipelines, gates, evidence) and running it with AI agents under explicit governance. Terraform is to infrastructure and Kubernetes to containers what ASAC aims to be to the SDLC.

> **Status: specification v0.4 (frozen).** The reference implementation works: the CLI (`validate`, `plan`, `apply`, gates, evidence, audit), the web portal, the Docker runner for `delegate` steps and the Claude Code harness (including MCP servers). The other harnesses (Codex, Cursor, Bob, Antigravity, Copilot) only hand off, and the registry is not implemented yet. This repository contains the language specification, the reference implementation, documentation and a verified example project.

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
