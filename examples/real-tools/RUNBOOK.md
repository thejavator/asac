# Runbook: run a two-step pipeline with Claude Code

About 15 minutes. ASAC launches `claude -p` for each step inside its own git worktree, checks the
result with hooks, and stops at a human gate. Nothing moves forward until you approve.

**What this proves, and what it does not.** With the sandbox on, the agent cannot rewrite the
hooks or the manifest, delete the audit, read your SSH keys or reach a domain you did not list.
If it tries to change a rule anyway, the step is blocked and the audit says which file. It does
not prove the agent's work is good: you still review it at the gate.

## 0. Prerequisites

```bash
git clone <this repository> && cd <this repository>/asac
uv sync                       # or: pip install -e .
asac doctor -f examples/real-tools/asac.yaml
```

`asac doctor` says what is missing and how to install it. You need `git`, `opa`, `node` 22.12 or
newer, `srt` and `claude` (logged in, or with `ANTHROPIC_API_KEY`).

## 1. Make a scratch project

The run starts from the last commit, so the project must be a clean git repository.

```bash
export WORK="$(mktemp -d)/real-tools"
cp -R examples/real-tools "$WORK" && cd "$WORK"
cp vars/claude-code.yaml asac.vars.yaml
git init -q && git add -A && git commit -qm "start"
export ASAC_STATE_DIR="$WORK/../asac-state"
asac doctor
asac validate
```

## 2. Turn the sandbox on

```bash
export ASAC_SANDBOX=1
export ASAC_SANDBOX_DOMAINS="<host of your model API, e.g. api.anthropic.com>"
```

Only the hosts you list are reachable. Other hosts are refused; so is everything else the agent
has no business touching (see *Limits*).

## 3. Run

```bash
asac apply -p feature --run-id demo
```

Expected: exit code 2, `waiting for gate gate_demo_requirements`. ASAC created the worktree
`$ASAC_STATE_DIR/worktrees/demo` on branch `asac/demo`, launched Claude Code there, ran the
hooks, and made a commit. Look at what it produced and at the commit the gate is about:

```bash
asac gates                    # the commit the gate approves is shown as commit=<sha>
git -C "$ASAC_STATE_DIR/worktrees/demo" show --stat HEAD
cat "$ASAC_STATE_DIR/worktrees/demo/SPEC.md"
```

## 4. Decide

If the spec is good, approve. This records the evidence `spec_reviewed` and starts `development`:

```bash
asac approve gate_demo_requirements --role product_owner --by you
```

If it is not, reject with a reason (the reason is part of the audit):

```bash
asac approve gate_demo_requirements --role product_owner --by you --reject --comment "criteria are vague"
```

A rejection ends the run (`failed`). It does **not** send the reason back to the agent: the
branch `asac/demo` keeps what was produced, for you to look at. `asac apply --resume demo --reopen`
reopens the same gate on the same commit; to get a better result, start a new run
(`--run-id demo2`), or put the check you care about in a `loop` (below) so the agent is told why.

The `development` step runs next, and stops at `gate_demo_development`. Its `tests-green` hook
ran the project's real tests in the worktree before the gate opened: a failing test blocks the
step (exit 3) instead of reaching you as finished work.

```bash
asac approve gate_demo_development --role product_owner --by you
```

## 5. Look at the result

```bash
asac status
asac logs demo                # every decision, in order
asac evidence verify demo
git -C "$WORK" log --oneline asac/demo
```

The work is on the branch `asac/demo`. Review and merge it yourself, then free the worktree:

```bash
asac clean demo
```

## Retry until the checks pass

A step can loop: when its checks fail, ASAC relaunches the agent with the reason, up to a hard
cap. In `asac.yaml`, on the step:

```yaml
loop: { until: [tests-green], max_iterations: 3 }
```

Each turn is audited as `step.iteration`. If the checks never pass, the step fails; it is never
validated.

## Limits you should know

- **The sandbox only reaches the model API.** `srt` re-signs TLS; hosts other than the model
  gateway fail certificate checks. The agent therefore cannot download dependencies.
- **Identity is declared.** `--by` and `--role` are not authenticated on the command line.
  Anyone who can run `asac` can approve as any role.
- **Cost is an estimate.** It comes from Claude Code's own report; behind a gateway it may not be
  a billed amount. A step that reports no cost blocks a run that has a cost budget.
- **One tool.** Claude Code is the only tool tested for real. Codex, Cursor, Bob and Antigravity
  mount their files but are not covered by the sandbox or the checks above.
- **Linux is not tested.** The sandbox was verified on macOS only.

## Doing a step by hand

Without `autorun`, ASAC prepares the brief and stops. You run the tool yourself in the worktree,
then record the evidence with `asac evidence bootstrap demo --evidence <id> --by you` and approve.
The hooks still check the result; ASAC cannot prove the tool was run.
