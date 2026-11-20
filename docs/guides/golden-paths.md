# Golden Path templates

!!! info "Status"
    Golden Paths are **not a language primitive**. They are a catalogue of ready-to-use ASAC *templates*, planned for the registry and deferred to [v0.5](../project/roadmap.md). This page documents the design.

A Golden Path is an ASAC project skeleton an organisation recommends, for example `golden/java-hexagonal`.

## Template vs module

| | Copied into your repo | Referenced from the registry |
|---|---|---|
| What | Skeleton, local conventions, instructions | Versioned **governance**: policies, gates, evidence types |
| Why | The team owns and adapts it | Security updates it centrally, with versions |

```bash
asac init --template golden/java-hexagonal
```

```yaml
modules:
  governance:
    source: registry.asac.dev/golden/java-hexagonal-policies
    version: "~> 2.1"
```

## Example catalogue (ideas)

`java-hexagonal`, `node-clean-arch`, `data-pipeline`, `hotfix-only`.

A Golden Path can ship its own evidence types, for instance an architecture-conformance check backed by ArchUnit or dependency-cruiser, together with the skill that produces them. That is why `arch_conform` is not in the core.
