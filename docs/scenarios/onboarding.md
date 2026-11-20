# Onboarding a new developer

Sara joins the payments team. She has never used ASAC.

1. **Clone.** `asac.yaml` already describes how the team delivers; no process document needed.
2. **Configure.** She copies `asac.vars.yaml.example` and fills in her tokens. She prefers Cursor, so she sets `dev_harness: cursor` locally (git-ignored). The team's manifest is unchanged. `asac validate` confirms Cursor is valid because her step runs in `assist` mode.
3. **Explore.** `asac status` shows active runs, pending gates and recent deliveries.
4. **Plan.** `asac plan --pipeline feature --trigger jira:PAY-1240` shows which steps run on the server and which run in her own IDE, before anything executes.
5. **Execute.** The dev agent works inside Cursor; she reviews and approves each change as if a colleague were working in her IDE.
6. **Portal.** Team metrics (deployment frequency, lead time, MTTR, change-failure rate) and maturity per capability show her role in governance.

!!! note
    Because Cursor is IDE-only, it is valid only for `assist` steps. If a team step were `delegate`, validation would reject the override. See the [harness rule](../concepts/harness.md#the-ide-only-rule).
