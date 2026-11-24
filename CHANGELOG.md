# Changelog

See [docs/project/changelog.md](docs/project/changelog.md) for the specification changelog.

## Unreleased

- Delegated steps run for real (`mode: delegate` + `execution: { runner: docker }`): the real
  `claude` ran in the real container, 0.35 USD. The engine now books the cost from the tool's
  report, loops on a failing check, relaunches after a reasoned rejection (no `autorun` needed),
  and sends the agent the check's output or the rejection reason. Before, a delegated step ran but
  its cost was never recorded, its loop never turned and a rejection did not relaunch it.
  `runner.started` records the network. A report with no cost is an unknown cost, never zero.
- `asac apply --enqueue` and `asac worker [--once]`: a run put in the job queue is taken by a worker
  that runs it. A job ends done when the run completes, waits at a gate or is blocked; an engine
  error puts it back with its reason, up to 5 attempts. The `JobQueue.claim` port takes an optional
  `kind`, in both adapters (SQLite and Postgres), so a worker leaves other kinds of jobs alone.
- Guide: delegated steps, the container's mounts, what the network does not do, the worker.
- Security: the commit ASAC makes at the end of a step no longer trusts the worktree's own `.git`
  file. An agent that can write its worktree could rewrite that file to point at a repository it
  made, whose configuration names a command (`core.fsmonitor`, `core.hooksPath`, `core.pager`), and
  ASAC's git, run on the host outside the sandbox, ran it. ASAC now reads the real git directory
  from the main repository and runs git with those settings off. The portal's file list follows
  the same rule. Reproduced under `srt` before the fix.
- The Docker runner (`mode: delegate`) gives the container one folder, the run's worktree,
  writable at `/work`. The main checkout and the state folder are not mounted. A run without a
  worktree is refused, never given the project. The default image is `asac-agent:<version>`
  (Claude Code, git, python3); `asac doctor` says if it is missing and how to build it, and
  checks a `runner_network` you name.
- `init`, `run`, `vars` and `learn` are in `asac --help`. `asac init --template feature` writes a
  project that validates with no warning and reaches its first gate (two skills, an instruction,
  three hooks, a values example, a `.gitignore`); `--template minimal` writes only an empty
  `asac.yaml`. The templates ship in the wheel.
- `asac vars check` and `asac vars diff` work before `asac.vars.yaml` exists: they list each
  variable without a default as `missing: <name>` (exit 1) instead of "not found".
- The live notification test now starts: its receiver imported modules removed from Python 3.12.
  Signed webhook, Slack, Teams and SMTP are checked with real sockets and a receiver in another
  process (`ASAC_NOTIFY_LIVE=1`). A failed send names the kind of failure and never the address.
- Documentation: the CLI reference lists every command with its real options; the quick start runs
  `init`, `vars check`, `validate`, `plan`, `apply`, `submit`, `approve`; `init --mode observe`
  (an option that does not exist) is gone from the docs.

- `asac validate` refuses a `mode: delegate` step with no `execution.runner` (`ASAC028`), where it used to fail only when the run reached the step. `runner_kind: fake` gives the in-memory runner for offline tests.

- `tests/test_real_claude.py`: the real `claude` on a project that is not the example, skipped unless
  `ASAC_REAL_CLAUDE=1`. See the contributing guide.

- The sandbox's refusals are in the audit: `sandbox.denied` with the file or host the tool was
  refused, read from the tool's own output and srt's log, capped at 20 per step. `asac audit` prints
  the detail of `sandbox.denied`, `integrity.violated` and `gate.denied`.

- `asac validate` warns (`ASAC027`) about keys it accepts but 0.1 does not apply: `knowledge`,
  `specLevel` and a provider's `config.model`. Before, they were accepted without a word.

- `asac submit <run>`: hand back the step you worked on. Its checks run first; its evidence is
  recorded only if they pass. A failed check returns the step to you with the reason.
- `asac apply` says where to work (the run's worktree) and how to hand the step back.
- Fixed: `asac evidence bootstrap` used to record a step's evidence before its hooks ran, so a
  `tests_green` evidence existed while the tests failed, and `evidence verify` said ok.

- Hooks per step: `steps.<id>.hooks.pre_tool` and `.post_step` list the declared hooks a step runs,
  after the global ones. A step no longer has to guard its script by step name.
- `asac validate` refuses a duplicated key in a manifest instead of keeping only the last one.
- The audit records when a hook ran (`pre_tool` or `post_step`), and the portal shows it.
- A run started from the portal now gets its own worktree, like one started by the CLI.
- `asac portal --local` for a developer, `asac portal --project ID=PATH` for a shared portal.

## 0.1.0 (2026-11-21): first supported path

Version 0.1 supports one path end to end: `doctor`, `validate`, `apply`, `approve`, `gates`,
`status`, `logs`, `audit`, `evidence`, `clean`, `kill`, with Claude Code as the only tool.

- Each run works in its own git worktree on branch `asac/<run>`; the main checkout is never
  written. ASAC makes the commit of each step and the human gate is bound to that commit.
- Hooks run in the worktree but are read from the main checkout; a step that changes a rule
  (`asac.yaml`, `asac.vars.yaml`, `.asac/`) is blocked and audited (`integrity.violated`).
- `step.loop`: retry the agent with the reason its work was rejected, with a mandatory cap.
- OS sandbox (`srt`, `ASAC_SANDBOX=1`): write only in the worktree, no secrets, listed hosts only.
- Real cost from `claude -p --output-format json`; an unknown cost blocks a cost budget.
- `asac doctor` and `asac clean`.

Not supported in 0.1, present in the repository: the web portal and daemon, the forge adapters,
the Docker and Kubernetes runners, the other harnesses, MCP, Postgres. The registry is not
implemented. Known limits: the sandbox reaches the model API only; approval identity is declared
on the command line; macOS only.

## Repository

- Initial public release of the v0.4 specification documentation, example project and tooling.
