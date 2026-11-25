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

## Three more complete examples

Each has its own README that says what every key does and what the version does not apply.

| Example | Case |
|---|---|
| [`spring-angular-postgres`](https://github.com/asac-dev/asac/tree/main/examples/spring-angular-postgres) | Java Spring backend, Angular frontend, PostgreSQL: migration, parallel backend and frontend, API contract |
| [`mobile-app`](https://github.com/asac-dev/asac/tree/main/examples/mobile-app) | Flutter app: a design tool and a coding tool, accessibility and permissions, a real device |
| [`php-ecommerce`](https://github.com/asac-dev/asac/tree/main/examples/php-ecommerce) | PHP e-commerce: a payment-change pipeline, money types, separation of duties |

`tests/test_examples.py` runs every pipeline of each one from its first step to `completed`.
