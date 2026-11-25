# ASAC — Agentic SDLC as Code

> **Declare your software delivery. Let agents execute it.**

ASAC is an open, declarative framework for describing a software delivery lifecycle as code (capabilities, agents, pipelines, gates, evidence) and running it with AI agents under explicit governance. Terraform is to infrastructure and Kubernetes to containers what ASAC aims to be to the SDLC.

> **Status: specification v0.4 (frozen), reference implementation 0.1.** **Version 0.1 supports one path, end to end:** `init`, `validate`, `plan`, `apply`, `run`, the Claude Code harness, hooks and Rego checks, `submit` for work done by hand, a human gate bound to a commit, `approve`, `evidence verify`, `audit`, `clean`, plus `doctor`, `vars`, `learn` and the step `loop`. A step can also be **delegated** to an agent in a Docker container, and a worker runs queued runs (see [the guide](docs/guides/delegate.md)) Each run works in its own git worktree, and with the sandbox on (`srt`) the agent cannot rewrite the rules, delete the audit, read your keys or reach other hosts. **Not supported in 0.1:** the web portal and daemon, the forge adapters, the Kubernetes runner, domain filtering of the container's network, the other harnesses (they only mount files), MCP and Postgres. Their tests use fakes, never the real system. The registry is not implemented. See [SCOPE_V1.md](SCOPE_V1.md) and [asac-specs-v1.md](asac-specs-v1.md).

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

Four projects, each with its `asac.yaml`, values file, skills, hooks and Rego policies. CI validates each manifest and runs `opa test` on its policies.

| Example | Case | What it shows |
|---|---|---|
| [`payments-service`](examples/payments-service) | Payments backend | The three layers, a quality gate, a policy tested with `opa` |
| [`spring-angular-postgres`](examples/spring-angular-postgres) | Java Spring backend, Angular frontend, PostgreSQL | A Flyway migration step, backend and frontend in parallel, an API-contract check, an MCP server on the database |
| [`mobile-app`](examples/mobile-app) | Flutter app (iOS and Android) | Different tools per step, accessibility and permission checks, a gate held in front of a real device |
| [`php-ecommerce`](examples/php-ecommerce) | PHP e-commerce (Symfony) | A separate pipeline for payment and price changes, money-type and scope checks, separation of duties |
| [`real-tools`](examples/real-tools) | Run with the real Claude Code | The [runbook](examples/real-tools/RUNBOOK.md): worktree, sandbox, hooks, a human gate |

## Versioning

Language spec and reference implementation are versioned separately. See [docs/project/versioning.md](docs/project/versioning.md).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) and the [Code of Conduct](CODE_OF_CONDUCT.md). Report vulnerabilities as described in [SECURITY.md](SECURITY.md).

## License

Apache License 2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
