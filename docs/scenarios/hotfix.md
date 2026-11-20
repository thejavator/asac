# Hotfix: accelerated pipeline

Production bug (P1): email notifications are not sent for USD transfers. The `hotfix` pipeline is shorter, but **SAST remains mandatory**.

| Property | Value |
|---|---|
| Trigger | Manual (no automatic trigger for hotfixes) |
| Timeout | 4 h (vs 72 h for `feature`) |
| Skipped | spec step, coverage gate |
| Never skipped | SAST gate |

```bash
asac apply --pipeline hotfix --trigger jira:PAY-BUG-89
```

1. The developer reports the bug; the dev agent works in `assist` mode, analyses logs and proposes a one-line fix (adding USD to a currency filter). The developer approves, and a regression test is added.
2. The QA agent runs SAST only: 0 findings. The gate passes automatically.
3. The DevOps agent checks policy: issue type is Bug, priority is P1, a ticket is attached. It merges and deploys **directly to production**, as configured in the hotfix pipeline.

Result: about 42 minutes from trigger to production, one human approval, one regression test.

| Evidence | Status |
|---|---|
| `spec_reviewed` | skipped (no spec step) |
| `tests_green` | produced |
| `sast_clean` | produced |
| `coverage_passed`, `qa_approved` | skipped (hotfix mode) |
| `deployed` | produced (production) |
