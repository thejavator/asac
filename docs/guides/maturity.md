# Maturity levels L0–L4

Maturity is measured **per capability**: a project can be L3 on specification and L1 on deployment.

| Level | Name | Mechanism |
|---|---|---|
| L0 | Human only | Observe mode: ASAC describes, nothing runs |
| L1 | AI assisted | `mode: assist` |
| L2 | Human directed | `assist` + gates |
| L3 | Agent executed | `mode: delegate` with gates |
| L4 | Policy governed | `autonomy: autonomous`, backed by a written doctrine and `.rego` policies |

Mapping to `autonomy`: `readonly` ≈ L0–L1, `review` ≈ L2–L3, `autonomous` ≈ L4 (proven capabilities only).

**Rule: never delegate before proving you can assist.** Promote a capability one level at a time, using the evidence and eval results the previous level produced.
