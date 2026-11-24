# Running an agent without a person: delegated steps and the worker

A step with `mode: delegate` is done by an agent that nobody sits in front of: on a server, in CI.
ASAC starts a container, runs the agent in it, and treats the result like any other step: the cost
is booked, the checks run, a failing check sends the agent back (`loop`), a reasoned rejection sends
it back too, the rules are fingerprinted around the run, then ASAC commits and the gate opens on that
commit. Nothing else changes: the same pipeline works by hand, under `autorun`, or delegated.

## 1. Declare it

```yaml
steps:
  development:
    capability: implementation
    agent: developer
    mode: delegate
    execution: { runner: docker }          # required: `asac validate` refuses a delegate step without it
    loop: { until: [tests-green], max_iterations: 3 }
    gate: { type: human, role: product_owner, timeout: 24h }
```

`execution.fallback: assist` hands the step to a person when the runner is not available
(`runner.unavailable` in the audit). Only `claude-code` can be delegated.

## 2. Build the agent image once

```bash
asac doctor            # says whether the image is built, and prints the command if it is not
```

The command builds `asac-agent:<version>`: Claude Code (version pinned in the Dockerfile), git and
python3, and **no credential**. The image is large (about 800 MB); nothing publishes it.

## 3. Set the runner

In `asac.vars.yaml`:

```yaml
runner_kind: docker
runner_env: ANTHROPIC_API_KEY,ANTHROPIC_BASE_URL     # names of variables passed to the container
runner_network: asac-egress                          # a Docker network you prepared (see below)
```

The key is passed **by name**: Docker reads the value from ASAC's environment, so it never appears on
a command line, in an image or in a file. If the agent prints it, ASAC masks it in the audit and in
the stored output.

## What the container is given

| | |
|---|---|
| The run's worktree | the only folder from the host, writable, at `/work` |
| `asac.yaml`, `.asac/`, the hook scripts, `.asac-state/`, your home | **not mounted**: the agent cannot read or change them |
| The root filesystem | read-only; `/tmp` is a 64 MB scratch space |
| User and privileges | user 65534, all capabilities dropped, `no-new-privileges`, 128 processes, 1 CPU, 512 MB |

The worktree is a checkout, so it holds its own copy of the tracked rules. The agent can rewrite that
copy; it is not what runs. ASAC runs the hooks of the **main** checkout, on the worktree's files, and
the commit it makes is made by ASAC, on the host, with git pointed at the real git directory (never at
the worktree's own `.git` file, which the agent can rewrite).

## What the network does not do

By default the container has **no network** (`none`), which also cuts the model API: the agent cannot
reach its model. For a real agent you name a Docker network (`runner_network`) that reaches your
model gateway and nothing else, and you set its egress rules (firewall, proxy, gateway) **outside
ASAC**. `asac doctor` checks that the network exists.

- ASAC does **not** filter by domain.
- A request the network refuses is **not** in the audit. Under `srt` (`autorun` with `ASAC_SANDBOX=1`)
  each refusal is audited as `sandbox.denied`; Docker has no equivalent. `runner.started` records the
  network the container was on, so a reader can tell what it could reach.

Domain filtering and the audit of network refusals are planned for a later version.

## 4. Queue a run and let a worker take it

```bash
asac apply -p feature --enqueue          # job 1 queued: run run_feature_ab12cd34 (feature). Start a worker: asac worker
asac worker                              # runs jobs until you stop it (Ctrl-C)
asac worker --once                       # handles the jobs that are due, then stops
```

`--enqueue` accepts `--run-id` and `--harness`; it runs nothing. The worker prints one line per job:
the job number, the run, and what the engine answered.

```text
job 1  run_feature_ab12cd34  waiting for gate gate_run_feature_ab12cd34_requirements
job 2  run_feature_cd34ef56  requirements handed to a person (brief: …)
```

The second line is a step in `mode: assist` with no `autorun`: the run waits for a person, and the
job is done (see the table below).

The queue is `jobs.db` in the state folder. What the worker does with the result:

| The engine answers | The job |
|---|---|
| completed, waiting at a gate, blocked | **done**: a person acts next, running it again would change nothing |
| error | back in the queue with the reason, up to **5 attempts**, then `failed` with the reason |
| (the worker dies mid-run) | after the lease (30 minutes) another worker takes it; a run that exists is resumed, not recreated |

The worker is sequential: one job at a time. The queue also carries other kinds of jobs; the worker
only takes `run` jobs and leaves the rest untouched.
