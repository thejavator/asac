# Evidence and gates

## Evidence

An **evidence type** is a named proof that a step was done correctly: `spec_reviewed`, `tests_green`, `sast_clean`. Evidence types are first-class citizens of the language.

- A step may start only when every evidence in its `requiresEvidence` exists.
- A step declares what it `producesEvidence`.
- Evidence is **immutable** once produced, timestamped, and stored in the [state](../reference/state.md).
- The set of types is **extensible**: a registry module (for example a Golden Path) can declare its own `evidenceTypes` together with the skill that produces them.

If a required evidence is missing or failed, the pipeline stops. There is no deployment without proof.

## Gates

A gate is a control point attached to a step. The core is deliberately minimal.

| Type | Meaning |
|---|---|
| `human` | A person with a given `role` must approve (with an optional `timeout`) |
| `quality` | A policy decides (usually a Rego file). It also needs a `role`, the person accountable for the verdict |

A `human` or `quality` gate without a `role` is refused by `asac validate` (ASAC020). A rejection needs a reason: `asac approve <gate> --reject --comment "..."` is refused otherwise. The portal enforces the same rule. A rejected run can be reopened with `asac apply --resume <run-id> --reopen`.
| `automated` | A deterministic check, no human |

```yaml
gate: { type: human, role: product_owner, timeout: 24h }
gate: { type: quality, role: qa_engineer, policy: .asac/policies/qa-gate.rego }
```

Complex logic never goes inline in the manifest. It goes to a separate Rego file (layer 3), which security can test and review on its own. See [Writing policies in Rego](../guides/policies.md).

## Evidence produced by people

Approving a human gate is itself an evidence-producing act: Alice approving a spec produces `spec_reviewed`, stamped with her identity and time.
