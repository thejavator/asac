# Versioning

Two independent version lines exist. Do not confuse them.

| Line | Current | Meaning |
|---|---|---|
| **Language specification** | **v0.4 (frozen)** | The language: resources, attributes, evidence types, interfaces. Declared in a manifest as `asac.spec: "0.4"`. |
| **Reference implementation** (CLI, runner, portal, registry) | **not released** | Working (CLI, portal, Docker runner, Claude Code harness); will follow its own semver, starting at `0.1.0`. Registry still to come. |

- The spec is pre-1.0: breaking changes are allowed between minor versions and are always listed in the [changelog](changelog.md).
- v0.4 is frozen: only corrections, no new features. New ideas go to the [v0.5 backlog](roadmap.md).
- Documentation and examples state the spec version they target.
