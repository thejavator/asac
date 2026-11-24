# Quick start

!!! note "Status"
    This page runs the path version 0.1 supports, with Claude Code working by hand. For the
    automatic path (the agent launched by ASAC, inside a sandbox) follow the
    [runbook](https://github.com/asac-dev/asac/blob/main/examples/real-tools/RUNBOOK.md).
    `asac doctor` checks your machine first.

## 1. Create the project

In a git repository with at least one commit:

```bash
asac init --template feature
cp asac.vars.yaml.example asac.vars.yaml
asac vars check                 # exit 0: every variable has a value
asac validate                   # 0 error(s), 0 warning(s)
git add -A && git commit -m "Add ASAC"
```

`asac init --template feature` creates `asac.yaml`, two skills, an instruction, three hooks,
`asac.vars.yaml.example` and `.gitignore` entries for `asac.vars.yaml` and `.asac-state/`. Before
you copy the example, `asac vars check` lists what is missing (`missing: tool`, exit 1).

The hook `tests-green.sh` runs `python3 -m unittest discover`. On another stack, edit it to run
your own tests.

## 2. See the plan

```bash
asac plan -p feature
```

```text
pipeline feature: 2 steps in 2 levels
  [0] requirements   capability=specification_engineering agent=analyst mode=assist gate=human(product_owner)
       produces: spec_reviewed
  [1] development    capability=implementation agent=developer mode=assist gate=human(product_owner)
       requires: spec_reviewed
       produces: tests_green
estimated tokens: 40,000
```

## 3. Run, work, hand back

```bash
asac apply -p feature --run-id first      # exit 2: the step waits for you
```

ASAC created a worktree on the branch `asac/first` and says where to work. Open your tool there,
write `SPEC.md` with an "Acceptance criteria" section, then:

```bash
asac submit first
```

The step's check runs. If `SPEC.md` is missing, nothing is recorded and the step comes back to you
with the reason. If it passes, the gate `gate_first_requirements` opens (exit 2).

## 4. Decide

```bash
asac gates
asac approve gate_first_requirements --role product_owner --by you
```

This records the evidence `spec_reviewed` on the commit ASAC made, and starts `development`.
Work in the same worktree, `asac submit first` again (the `tests-green` check runs your tests),
then approve `gate_first_development`.

## 5. Read the result

```bash
asac status
asac logs first                 # every decision, in order
asac evidence verify first
git log --oneline asac/first    # the work: review and merge it yourself
asac clean first                # remove the worktree, keep the branch
```

Without `--run-id`, `asac run` creates the run and executes it in one command. After a failure,
`asac learn <run>` writes the list of what went wrong to `.asac/proposals/`.

## Try the example

```bash
cd examples/payments-service
opa test .asac/policies -v      # 7 tests
asac validate
```
