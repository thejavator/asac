# Contributing to ASAC

Thank you for helping build an open standard.

## What to contribute

- Language-spec proposals (RFCs): new resource types, composition patterns, gate-model extensions.
- Documentation fixes and translations.
- Skills, modules, providers, harness extensions, Rego policies.
- A reference runtime (parser, plan/apply engine, state).

## Spec changes

The spec is pre-1.0. **v0.4 is frozen**: only corrections are accepted. New features target the v0.5 backlog (`docs/project/roadmap.md`). Open an issue titled `RFC: <topic>` describing the problem, the proposal, alternatives and the layer(s) affected.

## Before opening a pull request

```bash
pip install zensical pyyaml
zensical build --strict
opa test examples/payments-service/.asac/policies
opa check --strict examples/payments-service/.asac/policies
python -c "import yaml,sys; [yaml.safe_load(open(f)) for f in sys.argv[1:]]" examples/payments-service/asac.yaml examples/payments-service/asac.vars.yaml.example
```

## Style

- English, short sentences, concrete examples.
- Never put secrets, real URLs or customer data in examples; use `example.com` and `${vault...}` references.
- Do not claim regulatory compliance; documents may *support* auditability.
- Mark anything not implemented as such.

By contributing you agree your work is licensed under Apache 2.0.
