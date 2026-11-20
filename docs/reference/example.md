# Complete example

The three files of one project, `payments-service`. Source in [`examples/payments-service`](https://github.com/asac-dev/asac/tree/main/examples/payments-service); the YAML is parsed and the Rego tested in CI.

## Layer 1: `asac.yaml`

```yaml
--8<-- "examples/payments-service/asac.yaml"
```

## Layer 2: `asac.vars.yaml.example`

```yaml
--8<-- "examples/payments-service/asac.vars.yaml.example"
```

## Layer 3: `.asac/policies/qa-gate.rego`

```rego
--8<-- "examples/payments-service/.asac/policies/qa-gate.rego"
```
