# Concepts

ASAC has a small vocabulary. Read in this order:

1. [The three layers](three-layers.md) — where each piece of configuration lives.
2. [Capability, skill, agent](capability-skill-agent.md) — separating *what* from *how*.
3. [Evidence and gates](evidence-and-gates.md) — how progress is proven and controlled.
4. [Harness](harness.md) — the agentic runtime, and why it is swappable.
5. [Execution model](execution-model.md) — `assist` vs `delegate`, and where steps run.
6. [Agent governance](governance.md) — knowledge, instructions, budgets, hooks, autonomy (v0.4).
7. [Six pillars mapping](six-pillars.md) — how ASAC covers harness engineering.

## The lifecycle: Declare → Plan → Apply → Evidence

ASAC follows the declarative cycle popularised by Terraform.

1. **Declare** — write `asac.yaml`: what the SDLC must do, not how.
2. **Plan** — preview who does what, estimated cost, and the human gates.
3. **Apply** — agents execute. Each step blocks on its gates and produces evidence.
4. **Evidence** — proofs are immutable in the state; the full audit trail can be exported.

## Two meanings of "harness"

*Harness engineering* is the discipline of designing everything around a model (instructions, knowledge, skills, tools, orchestration, control). The ASAC **`harness` resource** is narrower: the *runtime* that runs the agentic loop (for example Claude Code, GitHub Copilot, Cursor). See [Harness](harness.md).
