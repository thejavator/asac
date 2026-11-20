# Registry

Everything reusable across projects is published to a registry: skills, providers, modules, harness extensions, shared policies. Items are semver-versioned; skills ship embedded evals. The address `registry.asac.dev` is **planned**; no public registry exists yet.

## Skills (illustrative catalogue)

| Skill | Version | Purpose |
|---|---|---|
| `core/specification` | 2.1.0 | Business intent to structured spec and acceptance criteria |
| `core/quality-assurance` | 2.5.0 | Code review, tests, coverage, SAST; parameterisable |
| `core/release` | 1.8.0 | Merge, tag, changelog, deploy |
| `java/implementation` | 3.0.0 | Maven/Gradle, JUnit 5, Spring Boot aware |
| `node/implementation` | 2.4.0 | npm/pnpm, Jest, TypeScript aware |
| `python/implementation` | 1.9.0 | pip/uv, pytest, type hints |

## Modules (illustrative)

| Module | Purpose |
|---|---|
| `quickstart/java-microservice` | Agents, pipelines and default policies for a Java service |
| `quickstart/node-api` | Node.js REST API: feature, hotfix, deploy |
| `enterprise/release-train` | Multi-team release train with merge-freeze gates |

All names and versions above are examples of the intended catalogue, not published artefacts.
