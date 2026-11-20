# Quick start

!!! note "Status"
    The `asac` CLI, the portal and the Claude Code harness work today; `--harness fake` runs without any tool. Commands for the registry (`skill publish`, `registry search`, `provider install`) are not implemented yet. This page shows the workflow as defined by spec v0.4. You can already study and validate the [example project](https://github.com/asac-dev/asac/tree/main/examples/payments-service): its YAML parses and its Rego policy is covered by `opa test`.

## 1. Initialise

```bash
asac init                       # detects the stack, generates the three layers
cp asac.vars.yaml.example asac.vars.yaml
asac vars check                 # every var.* resolved?
asac validate                   # manifest, vars, policies, harness compatibility
```

`asac init` creates `asac.yaml`, `asac.vars.yaml.example`, `.asac/policies/` and a `.gitignore` entry for `asac.vars.yaml`.

## 2. Plan (nothing executes)

```bash
asac plan --pipeline feature --trigger jira:STORY-1234
```

```text
Plan: pipeline "feature" for STORY-1234
  Step 1 requirements  agent: ba      (assist)
  Step 2 development   agent: dev     (delegate)
  Step 3 verification  agent: qa      (assist)
  Step 4 release       agent: devops  (delegate)
Gates: 2 human · 1 quality
Cost:  ~38,000 tokens estimated
Apply? [y/N]
```

Use `asac plan --dry-run` to simulate a step's effects (actions and files touched) without applying them.

## 3. Apply

```bash
asac apply --pipeline feature --trigger jira:STORY-1234
```

Each step blocks on its gates and records evidence. Inspect with `asac status`, `asac logs <run-id>`, `asac evidence show`, and `asac audit`.

## Reusing a template

Instead of writing everything, start from a [Golden Path template](../guides/golden-paths.md):

```bash
asac init --template golden/java-hexagonal
```

## Try the example today

```bash
cd examples/payments-service
opa test .asac/policies -v      # 7 tests
python -c "import yaml; yaml.safe_load(open('asac.yaml'))"
```
