# The three layers

Each layer has a different audience, cadence of change and Git workflow. Mixing them in one file is a design error.

| Layer | File | Audience | Declares |
|---|---|---|---|
| **1 — Manifest** | `asac.yaml` | Tech lead, architect, PO | **What**: capabilities, agents, pipelines, evidence types, gates. No concrete values. Portable across teams. |
| **2 — Runtime config** | `asac.vars.yaml` | Ops, SRE, CI/CD | **Where / with what**: URLs, secret references, state backend, concrete harness choices. One file per environment, usually git-ignored. |
| **3 — Policies** | `.asac/policies/*.rego` | Security, governance, compliance | **Rules**: what agents may or may not do, written in [OPA/Rego](https://www.openpolicyagent.org/). Testable with `opa test`. |

!!! tip "How to tell you are in the wrong layer"
    - A secret, a concrete URL or Rego code in `asac.yaml` → wrong layer.
    - Logical structure in `asac.vars.yaml` → wrong layer. It holds **values only**.
    - A policy that cannot be tested in isolation → wrong layer.

## Why separate them

- The security team edits `qa-gate.rego`, tests it, and gets it reviewed in its own pull request, without touching the SDLC manifest.
- A developer changes their personal harness in their local `asac.vars.yaml`; the team's manifest is unchanged.
- The same manifest runs in dev, staging and production with different vars files.

## Connecting layers 1 and 2: variables

The manifest declares the variables it expects; layer 2 resolves them.

```yaml
# asac.yaml (layer 1)
variables:
  gitlab_token: { type: string, sensitive: true }
providers:
  gitlab:
    source: asac/gitlab
    config: { token: var.gitlab_token }
```

```yaml
# asac.vars.yaml (layer 2)
gitlab_token: ${vault.gitlab/deploy-token}   # resolved at run time
```

Secrets are references to a secret manager, resolved at execution time. Agents never see them: the MCP gateway injects credentials.

## Reserved keys in layer 2

Two keys configure the platform and are not `var.*` values: `state_backend` and `data_residency`. They never need a declaration in `variables:`, and `asac vars diff` does not report them as unused.

## How references are resolved

| Reference | Resolved against |
|---|---|
| Local path (`instructions[].ref`, `knowledge[].path`, hook `run`) | The repository on disk; a missing file is an error |
| Name defined by the spec (policy `no_regression`, built-in evidence types) | A built-in catalogue, not `.asac/policies/` |
| Registry reference (`registry...@x.y.z`) | The configured registry; skipped with a warning when none is configured |

## Analogy

Terraform uses `main.tf` (declaration), `terraform.tfvars` (values) and Sentinel/OPA (policies). ASAC applies the same pattern to the SDLC.
