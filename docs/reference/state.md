# State model

The state is the memory of the SDLC: source of truth for audit and for resuming after interruption. Evidence is immutable once produced.

```json
{
  "version": "1.0",
  "workspace": "payments-service",
  "run": "run_STORY-1234_20260930",
  "pipeline": "feature",
  "status": "in_progress",
  "steps": {
    "requirements": { "status": "completed", "agent": "ba", "mode": "assist" },
    "development":  { "status": "running", "agent": "dev" },
    "verification": { "status": "pending" },
    "release":      { "status": "pending" }
  },
  "evidence": {
    "spec_reviewed": {
      "status": "produced",
      "produced_by": "requirements",
      "approved_by": "alice@example.com",
      "at": "2026-09-30T09:45:00Z"
    },
    "tests_green": { "status": "pending" },
    "deployed":    { "status": "pending" }
  }
}
```

## Gates

Each human or quality gate has a stable `gate_id`, so it can be approved from the CLI, the portal or an integration.

```json
"gates": {
  "gate_run_STORY-1234_requirements": {
    "run_id": "run_STORY-1234_20260930",
    "step_id": "requirements",
    "type": "human",
    "role": "product_owner",
    "status": "approved",
    "requested_at": "2026-09-30T09:04:00Z",
    "timeout_at": "2026-10-01T09:04:00Z",
    "decided_by": "alice@example.com",
    "decided_at": "2026-09-30T09:45:00Z",
    "comment": null,
    "evidence_ids": ["spec_reviewed"]
  }
}
```

`status` is one of `pending`, `approved`, `rejected`, `expired`. Only a `rejected` gate can go back to `pending` (reopen). Audit events around gates: `gate.opened`, `gate.approved`, `gate.rejected` (the reason is the detail), `gate.denied` (the approver lacked the role), `gate.reopened`, `gate.expired`. The actor of a human decision is `Name (subject)`. A run waiting on a gate has the status `gate_waiting`.

## Execution and resume

Execution is stateless, resume is stateful. A command that reaches a human gate never waits for it: it persists the state, sets the run to `gate_waiting` and exits with code `2`. After the gate is decided, `asac apply --resume <run-id>` continues from the next step. Exit codes: `0` completed, `1` error, `2` waiting for a gate, `3` blocked by a policy or budget.

The backend is chosen in layer 2 (`state_backend`, for example `s3://…`). Stored under `.asac-state/` locally.

## State backends

The state store is a port. SQLite is the default and needs no setup. For a team deployment,
point `ASAC_STATE_URL` at a PostgreSQL database and install the extra:

```bash
pip install 'asac-cli[postgres]'
export ASAC_STATE_URL=postgresql://asac:secret@db.internal:5432/asac
```

Both backends pass the same conformance suite (`tests/conformance/test_state_store.py`).
In Postgres, evidence and audit are append-only through triggers, so a direct SQL client
cannot rewrite them, and gate decisions take a row lock so two approvers cannot both win.
