# Writing policies in Rego

Gate and governance logic lives in `.asac/policies/*.rego`, evaluated by [Open Policy Agent](https://www.openpolicyagent.org/). Never write Rego inline in the manifest.

## Example: the QA gate

```rego
--8<-- "examples/payments-service/.asac/policies/qa-gate.rego"
```

The gate's input (`findings_count`, `coverage`, `sast_high_count`, `human_approved`, `pending_hours`, `skill_params`) is provided by the gate engine. Rules named `block` return reasons; `escalate` signals a timeout.

## Testing

```bash
opa test .asac/policies -v
opa check --strict .asac/policies
```

The repository's own tests (`qa-gate_test.rego`) run in CI.

## Typical policies

- QA agent must differ from dev agent.
- No push to `main`.
- Hotfix pipeline: ticket type must be Bug with priority P1; SAST gate is never disabled.
- `no_regression`: a security score must not decrease between iterations.
