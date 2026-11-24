# CLI reference

!!! info "Implementation status"
    Version 0.1 supports the commands in `asac --help`: `init`, `doctor`, `validate`, `vars`,
    `plan`, `apply`, `run`, `worker`, `submit`, `gates`, `approve`, `status`, `logs`, `audit`, `evidence`,
    `learn`, `kill`, `clean` and `version`. `portal`, `daemon` and `project` exist and answer to
    their name, but they are not part of the supported path (see [Portal and daemon](portal.md)).
    Not implemented: `provider install`, `registry search`, `skill publish`.

    Harnesses: `claude-code` (the one tested for real) and `fake` (offline tests). `codex`,
    `cursor`, `bob`, `antigravity` and `copilot` mount the skill where the tool reads it and hand
    off; see `examples/real-tools`.

Every command that reads the project takes `--file/-f <asac.yaml>` (default `./asac.yaml`).

## Setup

| Command | What it does |
|---|---|
| `asac init [path]` | Create `asac.yaml` and `.asac/` (`policies`, `hooks`, `knowledge`, `instructions`), detecting the project's stack. `--template minimal` (default) writes an empty valid manifest and nothing else. `--template feature` writes a project that validates and reaches its first gate: a two-step pipeline (`requirements`, `development`), two skills, an instruction, three hooks (`no-secrets`, `spec-present`, `tests-green`), `asac.vars.yaml.example`, and a `.gitignore` with `asac.vars.yaml` and `.asac-state/`. `--name` sets the workspace name, `--force` replaces files that already exist (without it, `init` refuses and changes nothing). On a stack other than Python it says to edit `.asac/hooks/tests-green.sh` |
| `asac doctor` | Check git, opa, node (>= 22.12), srt and claude, and that the project is a clean git repository. Says how to fix each failure; exit 1 if a required one fails |
| `asac validate` | Check the manifest: syntax, unknown or duplicated keys, cross-references, `var.*`, Rego policies, mode and harness compatibility. Each problem carries a code (`ASAC001` to `ASAC028`; `ASAC028`: a `delegate` step with no `execution.runner`). `--json`, `--vars <file>` |
| `asac vars check` | Fail (exit 1) if a declared variable without a default has no value. Works before `asac.vars.yaml` exists: each such variable is listed as `missing: <name>` |
| `asac vars diff` | List missing variables (exit 1) and unused ones. Reserved keys are never unused |

## Execution

| Command | What it does |
|---|---|
| `asac plan` | Show the step order, gates and estimated tokens. Changes nothing. `--json` |
| `asac apply` | Create a run, its worktree and its branch `asac/<run>`, then execute the pipeline until a gate or the end. `-p <pipeline>`, `--run-id`, `--harness`. Exit 2 at a gate: it never waits unless `--watch` |
| `asac apply --resume <run>` | Continue a run where it stopped. `--reopen` first reopens the rejected gate |
| `asac apply --watch [--poll <s>]` | Stay in the foreground and continue after each decision until the run ends |
| `asac apply --enqueue` | Put a new run in the job queue for a worker and run nothing. Prints the job number. Takes `-p`, `--run-id`, `--harness`; not combinable with `--watch`, `--resume`, `--reopen` |
| `asac worker` | Take the queued runs and run them, one at a time, until stopped. `--once` handles the jobs that are due and stops; `--poll <s>` is the wait when the queue is empty. See [Delegated steps and the worker](../guides/delegate.md) |
| `asac run [step]` | Create a run and execute it, with the same exit codes as `apply`. With a step name, run only that step, after checking its dependencies and required evidence |
| `asac submit <run>` | Hand back the step you did by hand (no `autorun`). Its checks run; on failure nothing is recorded and the step returns to you with the reason; on success it goes to its gate. `--by <name>` is recorded |
| `asac kill <run>` | Stop a run for good (`run.killed`). The engine checks before every step; it cannot be resumed |
| `asac clean <run>` | Remove the run's worktree and keep its branch. Refused while the run is not finished unless `--force` |

## Decisions and evidence

| Command | What it does |
|---|---|
| `asac gates` | List gates, pending ones first. `--status` filters |
| `asac approve <gate>` | Approve a gate and continue the run. `--by <name>` and `--role <role>` are recorded with the commit sha. `--reject --comment "<reason>"` rejects, and the reason is required. A role the gate does not accept is refused with exit 3. `--no-resume` records the decision only |
| `asac evidence show <run>` | The evidence recorded for a run |
| `asac evidence verify <run>` | Check that every requirement of the run's completed steps is met |
| `asac evidence bootstrap <run> --evidence <id>` | Record a fact produced outside ASAC, such as an imported review. Marked as bootstrapped, never as a step's work |

## Reading a run

| Command | What it does |
|---|---|
| `asac status` | The runs, or `--run-id <run>` for its steps |
| `asac logs <run>` | The audit of one run, in order. `--json` |
| `asac audit` | The whole audit log, as text or `--format csv`. `--run-id` filters. The detail of `sandbox.denied`, `integrity.violated` and `gate.denied` is printed |
| `asac learn <run>` | Write `.asac/proposals/<run>.md`: the list of the run's failures, blocks and escalations (`proposal.written`). Observations only: ASAC applies nothing, you edit the manifest yourself |
| `asac version` | The implementation version and the spec version it targets |

## Not supported in 0.1

`asac portal`, `asac daemon` and `asac project` (see [Portal and daemon](portal.md)). `asac provider
install`, `asac registry search` and `asac skill publish` are not implemented.

## Exit codes

| Code | Meaning |
|---|---|
| `0` | Completed |
| `1` | Error |
| `2` | Waiting for a human gate or for manual work. `asac approve`, `asac submit` and `asac evidence bootstrap` continue the run themselves (`--no-resume` to opt out); `asac apply --watch` keeps following it; `asac apply --resume <run-id>` resumes after a crash or a block |
| `3` | Blocked by a policy, a budget, a hook, a role or a kill |
