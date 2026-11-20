# New feature: from Jira story to staging

A story is created in Jira. ASAC orchestrates agents and gates and produces a complete evidence chain, without the team changing its Jira workflow.

*Pipeline `feature` · maturity L3 · about 4–6 h excluding human gates · about 42,000 tokens.*

1. **09:00 — Opt-in.** Alice (product owner) creates story `PAY-1234` and adds the label `asac-enabled`. Without the label ASAC does not intercept the story: teams control what they hand to agents.
2. **09:00 — Trigger.** The daemon receives the webhook, detects the label and starts `run_PAY-1234`. First step: `requirements`, agent `ba`, mode `assist`.
3. **09:00–09:04 — Requirements.** The BA agent reads the ticket, finds similar stories in shared memory and produces 3 user stories and 7 acceptance criteria. It then waits on a gate.
4. **09:47 — Gate 1 (human, product owner).** Alice reviews in the portal and approves. Evidence `spec_reviewed` is produced and timestamped.
5. **09:47–11:23 — Development.** The dev agent (`delegate`) creates `feat/PAY-1234`, implements, writes tests, opens a merge request. Evidence: `tests_green`, `mr_created`.
6. **11:23–11:51 — Verification.** The QA agent, **different from the dev agent (enforced by OPA)**, checks coverage (89 % ≥ 85 %), SAST (0 high, 2 medium) and spec compliance. Two medium findings trigger a gate.
7. **12:14 — Gate 2 (quality + human).** The QA engineer approves despite findings with a comment, recording them as tech debt. Evidence: `qa_approved`, `coverage_passed`, `sast_clean`.
8. **12:14–12:22 — Merge and staging.** The DevOps agent verifies the whole evidence chain, merges and deploys to staging.
9. **15:02 — Gate 3 (human, product owner).** Alice approves the release from Slack or the portal. Evidence `deployed`.

## Resulting evidence chain

| Evidence | Produced by | Note |
|---|---|---|
| `spec_reviewed` | product owner | gate: human |
| `tests_green` | dev agent | 14 tests passed |
| `mr_created` | dev agent | |
| `coverage_passed` | QA agent | 89 % ≥ 85 % |
| `sast_clean` | QA agent | 0 high findings |
| `qa_approved` | QA engineer | 2 medium findings accepted |
| `deployed` | DevOps agent | staging, release approved |

Summary: 5 agent roles, 3 human gates, 7 evidences.
