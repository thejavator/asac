# Adopting ASAC on an existing project

Most teams already have a codebase in production. ASAC is adopted progressively, one step at a time, without breaking what works.

| | New project | Existing project |
|---|---|---|
| Start | `asac init --template feature`: full pipeline | `asac init`: an empty manifest, then one step at a time |
| Evidence | Clean chain from zero | Bootstrapped from existing tests |
| Maturity | L2–L3 possible from the first sprint | Start at L1, rise progressively |
| Pipelines | One | Legacy and feature pipelines coexist |

## Four phases

### 1. Observe (weeks 1–2)
Create an empty manifest. `asac init` detects the project's stack and writes only `asac.yaml` and the `.asac/` folders. **No agent runs.** Describe your conventions in `.asac/instructions/` and your checks in `.asac/hooks/` before you declare a step.

```bash
asac init
```

### 2. Assist (month 1)
Enable a single step in `mode: assist`: the agent proposes, humans validate everything. Start with the least risky capability (specification or code review).

### 3. Bootstrap (month 2)
Produce baseline evidence for the modules you want to cover. Bootstrapped evidence is **marked differently** from evidence produced by agents, and dashboards distinguish them.

```bash
asac evidence bootstrap --scope payments/core
```

### 4. Delegate (months 3–6)
New features move to `mode: delegate` with automatic gates. Legacy code stays in `assist`. Both pipelines coexist:

```yaml
pipelines:
  feature:          # new stories: L3, full gates
    steps:
      development: { mode: delegate }
  legacy-refactor:  # existing code: L1, everything in assist
    steps:
      development: { mode: assist }
  hotfix: {}        # urgent: minimal gates, SAST only
```

!!! quote "Fundamental rule"
    Never delegate before proving you can assist. See [Maturity levels](../guides/maturity.md). The durations above are indicative.
