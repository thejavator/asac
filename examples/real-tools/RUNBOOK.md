# Runbook: run the pipeline with a real AI tool

You are the human in the loop. ASAC mounts the skill and stops; the tool works only when you
launch it; nothing moves forward until you record evidence and approve. Run the blocks in
order, in one terminal (zsh/bash). Nothing here edits the repository: you work in a copy.

## 0. Set up a scratch copy

Pick the tool: `claude-code`, `codex`, `cursor`, `bob` or `antigravity`.

```bash
export TOOL=codex
export ASAC_BIN=/Users/tahrielmedhi/IBM/sldc-agentic/asac/.venv/bin   # folder that holds `asac`
export PATH="$ASAC_BIN:$PATH"
export WORK="$(mktemp -d /tmp/asac-real-$TOOL.XXXXXX)"
cp -R /Users/tahrielmedhi/IBM/sldc-agentic/asac/examples/real-tools/. "$WORK"
cd "$WORK" && cp vars/$TOOL.yaml asac.vars.yaml && export ASAC_STATE_DIR="$WORK/.asac-state"
```

## 1. Validate, then start the run (mounts the skill, stops at the first human step)

```bash
asac validate
```

```bash
asac apply -p feature --run-id demo
```

Expected: exit code 2, "requirements handed to a person". Files mounted for your tool:

| Tool | Mounted file |
|---|---|
| claude-code | `.claude/skills/spec/SKILL.md`, `CLAUDE.md` |
| codex | `AGENTS.md` |
| cursor | `.cursor/rules/asac-spec.mdc` |
| bob | `.bob/skills/spec/SKILL.md` |
| antigravity | `.agent/skills/spec/SKILL.md` |

The task for the tool is in `.asac-state/briefs/demo/requirements.md`.

## 2. Step `requirements`: the tool writes a spec

Run the tool on this step only. Copy the line for your tool (needs the tool to be logged in;
it uses your account). It must not touch `app/`.

```bash
claude -p "Read .asac-state/briefs/demo/requirements.md and the mounted ASAC skill. Write a short spec with acceptance criteria in SPEC.md for: done() must raise ValueError when the title is unknown. Do NOT change anything under app/." --permission-mode acceptEdits
```

```bash
codex exec -s workspace-write --skip-git-repo-check -C "$WORK" "Read .asac-state/briefs/demo/requirements.md and the mounted ASAC skill. Write a short spec with acceptance criteria in SPEC.md for: done() must raise ValueError when the title is unknown. Do NOT change anything under app/."
```

```bash
cursor-agent -p -f "Read .asac-state/briefs/demo/requirements.md and the mounted ASAC skill. Write a short spec with acceptance criteria in SPEC.md for: done() must raise ValueError when the title is unknown. Do NOT change anything under app/."
```

Bob and Antigravity are GUI apps: open the folder, check that the mounted skill is listed, and
give them the same prompt as above.

```bash
bobide "$WORK"
```

```bash
open -a Antigravity "$WORK"
```

Review `SPEC.md`. If it is good, record your decision:

```bash
asac evidence bootstrap demo --evidence spec_reviewed --by you
asac approve gate_demo_requirements --role product_owner --by you
```

Both commands continue the run by themselves (add `--no-resume` to only record the decision).
The second one reaches `development` and writes `.asac-state/briefs/demo/development.md`.

## 3. Step `development`: the tool implements and tests

Same tool, same pattern. Copy the line for your tool.

```bash
claude -p "Read .asac-state/briefs/demo/development.md, the mounted ASAC skill and SPEC.md. Implement SPEC.md in app/todo/__init__.py and add a unit test in app/tests/test_todo.py. Run: cd app && PYTHONPATH=. python3 -m unittest discover -s tests" --permission-mode acceptEdits
```

```bash
codex exec -s workspace-write --skip-git-repo-check -C "$WORK" "Read .asac-state/briefs/demo/development.md, the mounted ASAC skill and SPEC.md. Implement SPEC.md in app/todo/__init__.py and add a unit test in app/tests/test_todo.py. Run: cd app && PYTHONPATH=. python3 -m unittest discover -s tests"
```

```bash
cursor-agent -p -f "Read .asac-state/briefs/demo/development.md, the mounted ASAC skill and SPEC.md. Implement SPEC.md in app/todo/__init__.py and add a unit test in app/tests/test_todo.py. Run: cd app && PYTHONPATH=. python3 -m unittest discover -s tests"
```

Check the result yourself with the real tests:

```bash
(cd app && PYTHONPATH=. python3 -m unittest discover -s tests -v)
```

Then record it. The `tests-green` hook runs the same tests again and blocks (exit 3) if they fail:

```bash
asac evidence bootstrap demo --evidence tests_green --by you
```

If the hook blocked, fix the code and run `asac apply --resume demo` again (a blocked run is
the one case where you resume by hand). Otherwise approve:

```bash
asac approve gate_demo_development --role product_owner --by you
```

## 4. Look at the result

```bash
asac status --run-id demo
asac audit
```

`asac audit` lists every decision: who recorded which evidence, who approved which gate.
Remove the scratch copy with `cd / && rm -rf "$WORK"` when you are done.

## What is checked and what is not

- Automated (`tests/test_real_tools_example.py`): validation, mounting for the five tools,
  hand-off, and the hook blocking when the real tests fail. No tool is launched.
- Not checked: that each tool reads the mounted file. Step 2 is that check; if the tool
  ignores the skill, tell us which tool.
- ASAC cannot stop a tool you launch yourself from editing files early. Only the future
  `delegate` mode (a runner starts the tool) can enforce that.


## Optional: let ASAC launch the tool for you

For `claude-code`, `codex` and `cursor`, `vars/<tool>.yaml` sets `autorun: true` in `asac.vars.yaml`, so the CLI, the portal and the daemon all launch the tool. `ASAC_AUTORUN=0` or `1` overrides it for one process; `autorun_timeout` (or `ASAC_AUTORUN_TIMEOUT`) sets the limit.
ASAC then runs the tool's non-interactive CLI for the current step only (output in
`.asac-state/briefs/<run>/<step>.log`, timeout `ASAC_AUTORUN_TIMEOUT`, default 900 s).
The human gates are unchanged: you still check the result, record the evidence
(`asac evidence bootstrap`), approve and resume. `bob` and `antigravity` are GUI tools and
are never launched. If the CLI is missing or exits non-zero, the step fails with that reason.


Each step now has its own skill (`.asac/skills/spec.md` for the analyst, `.asac/skills/impl.md`
for the developer), and the `tests-green` hook only runs after `development`.

## One command for the whole run

`asac apply --watch` stays in the foreground, continues after each approval or evidence, and
exits when the run is completed, failed or blocked. Combined with `ASAC_AUTORUN=1`, you only
make the human decisions (evidence, approve) from a second terminal.

## What ASAC checks, and what it cannot

- With `ASAC_AUTORUN=1` nobody types the tool command. The audit records `tool.launched`
  (tool, exit code, log path, SHA-256 of the log).
- The `step-scope` hook checks the result, whoever produced it: after `requirements`, `SPEC.md`
  must exist with acceptance criteria and `app/` must be unchanged (fingerprint before/after).
  A failure blocks the step (exit 3).
- With autorun there is no manual `evidence bootstrap`: the gate opens once the hooks pass, and the
  evidence is recorded when the `product_owner` approves it.
- Without autorun, `evidence bootstrap` is still a declaration by a person. The hooks still check
  the result, but ASAC cannot prove that the tool was run.
