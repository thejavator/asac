# Changelog

## Reference implementation (unreleased)

- **Added** an optional `mcp` block on providers (layer 2, spec v0.4 unchanged), validator codes `ASAC024` and `ASAC025`, and MCP wiring for Claude Code (`.mcp.json` per step, `--allowedTools`, `tools.exposed` audit).
- **Added** a sign-in screen that is also the portal home page, and `GET /api/v1/login-options`.

## Spec v0.4 (frozen)

- **Added** primitives `knowledge`, `instruction`, `budget`, `hook`.
- **Added** step attributes `autonomy` (`readonly`/`review`/`autonomous`) and `escalation`; pipeline `specLevel` (1–3); `discovery` pipeline.
- **Added** evidence `deps_verified`, `hills_defined`, `prfaq_approved`, `tda_signed`, `outcome_reviewed`; policy `no_regression`.
- **Added** skill pinning by digest and signature; CLI tools `asac plan --dry-run`, `asac kill`, `asac learn`.
- **Changed** data residency is declared in layer 2.
- **Clarified** evidence types are extensible by registry modules.

## Spec v0.3

- **Added** formal definition of the harness (runtime), skill adapters, execution model (`assist` → persona machine, `delegate` → headless runner), optional `execution` block.
- **Changed (breaking)** `asac/harness-interface@2.0`: `execute` split into `mount` + `run`; `getCapabilities` renamed `describe`.

## Spec v0.2

- **Added** three-layer model; `capability` and `evidenceType` as first-class resources; `mode` on the step.
- **Changed** harness becomes an extension point; skill = HOW; provider config through `var.*`; simplified gates.
- **Removed** inline Rego in the manifest.
