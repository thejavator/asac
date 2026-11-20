# Portal and daemon

Two small services share the engine and the state store with the CLI. They hold no second copy of the rules: an approval in the portal calls the same function as `asac approve`, and a webhook calls the same function as `asac apply --resume`.

## Portal (`asac portal`)

A React single-page app served by the portal under `/app/`, backed by the JSON API under `/api/v1` (OpenAPI at `/api/v1/openapi.json`). There are no server-rendered pages. Run `asac portal --host 0.0.0.0 --port 8080` behind a TLS proxy.

| Path | Purpose | Who |
|---|---|---|
| `/` | Redirects to `/app/` | Signed-in user |
| `/app/` | The web interface: projects, runs, Decision Room, audit, pipelines, administration (projects included) | Any signed-in user |
| `/api/v1/projects/{pid}/audit.csv` | Full audit export | `auditor` or `manager` |
| `/api/v1/logout` | Ends the session (POST, CSRF header) | Signed-in user |
| `/healthz` | Liveness probe, no session needed | Anyone |

### Starting and stopping runs

Owner, developer, product owner and admin can start a run from the Runs page. The page first shows the plan (steps, agents, gates, estimated tokens, run budget) and refuses to start when the estimate is over the run budget.

| Call | Purpose |
|---|---|
| `GET /api/v1/projects/{pid}/pipelines/{name}/plan` | The plan and its estimate. Any project reader |
| `POST /api/v1/projects/{pid}/runs` | Creates the run (`run_<pipeline>_<nnnn>`) and executes it in the background. Answers 202 with the run id |
| `POST /api/v1/projects/{pid}/runs/{run_id}/stop` | Marks the run killed, same as `asac kill`. Answers 409 when already completed or killed |

Both writes need the CSRF header and are audited (`run.created`, `run.killed`) with the user's name. A run that is working refreshes on its page every 2 seconds. A stopped run cannot be resumed.

### Sign-in

OIDC authorization code flow with PKCE (S256), `state` and `nonce`, ID-token signature, issuer, audience and expiry checks. Keys are fetched from the provider and refreshed once when the key id is unknown, so key rotation does not need a restart. Roles come from the claim named by `ASAC_OIDC_ROLES_CLAIM` (default `roles`).

| Variable | Meaning |
|---|---|
| `ASAC_OIDC_ISSUER` | Issuer URL; discovery is read from `/.well-known/openid-configuration` |
| `ASAC_OIDC_CLIENT_ID` | Client id |
| `ASAC_OIDC_CLIENT_SECRET` | Optional, for confidential clients |
| `ASAC_OIDC_REDIRECT_URI` | The portal's `/callback` URL |
| `ASAC_OIDC_ROLES_CLAIM` | Claim holding the role list |
| `ASAC_ENV=dev` | Local personas instead of SSO. The portal refuses personas otherwise |

### Controls

- Sessions are stored server side; the cookie is `Secure`, `HttpOnly`, `SameSite=Lax`, and a fresh session id is issued at login.
- Every state-changing API call needs the `X-CSRF-Token` header.
- The engine checks the gate role again on each decision. Hiding a button is not the control. A refused attempt is written to the audit log (`gate.denied`).
- Strict CSP (`default-src 'none'`), `nosniff`, `no-referrer`, `X-Frame-Options: DENY`, HSTS.
- Login and decision endpoints are rate limited per client address (login) and per user (decisions).

## Daemon (`asac daemon`)

Receives webhooks and starts or resumes runs. It never waits on a human gate.

| Endpoint | Purpose |
|---|---|
| `POST /webhooks/jira` | Jira issue events. Requires `X-Hub-Signature-256` (HMAC-SHA256 of the body with `ASAC_WEBHOOK_SECRET`) |
| `POST /webhooks/github` | GitHub `issues` events (`opened`, `labeled`). Same HMAC header; GitHub sends it when the webhook has a secret |
| `POST /webhooks/gitlab` | GitLab issue events (`open`, `update`). Requires `X-Gitlab-Token` equal to `ASAC_WEBHOOK_SECRET` (GitLab sends the secret itself, not an HMAC) |
| `GET /healthz` | Liveness probe |

A run id is `run_<pipeline>_<issue key>`, so a replayed webhook resumes the same run instead of creating a duplicate. Only issues matching a pipeline trigger (for example the `asac-enabled` label) start a run. An issue key with anything other than letters, digits and dashes is ignored. The first delivery writes a `run.triggered` audit entry (`provider:key:event`); the run page reads it to show the trigger.

GitHub and GitLab issue openings are both the event `issue_opened`:

```yaml
trigger:
  type: event
  provider: github        # or gitlab, jira
  event: issue_opened     # jira: issue_created
  filter: { labels: [asac-enabled] }
```

## Runner

`mode: delegate` steps go through the `Runner` port. The Docker adapter starts a container with no network, a read-only root, a non-root user and the project mounted read-only. A runner is built from the project variables (or `ASAC_RUNNER=docker`) by `asac apply`, the portal and the daemon alike: `runner_kind: docker`, `runner_image`, `runner_network` (default `none`) and `runner_env` (names of environment variables passed into the container, such as a model API key; values are never stored and are redacted from the output).

For a `delegate` step the harness returns the headless command (Claude Code: `claude -p`, with the permission mode of the step). The engine runs it in the container with the pipeline timeout (15 minutes at most), then records a `runner.output` audit entry with the exit code, the SHA-256 of the full output and the first 8,000 characters. A non-zero exit or a timeout fails the step, the container is always stopped, and the run stays resumable. With no runner and `fallback: assist`, the step is handed to a person. Claude Code, Codex and Cursor delegate; Bob and Copilot are assist only.

With `runner_kind: kubernetes` the step runs in a pod instead: one pod per step, no service-account token, read-only root, non-root user, all capabilities dropped, an `emptyDir` at `/work`. Variables: `runner_image`, `runner_k8s_namespace` (default `asac`), `runner_k8s_context`, `runner_k8s_pvc` (project mounted read-only), `runner_k8s_secret` (a Kubernetes Secret holding the keys listed in `runner_env`, passed by reference) and `runner_env`. It uses `kubectl` and the user's context; it is tested with fakes, not on a cluster.

## Job queue

The `JobQueue` port has a SQLite adapter (local) and a PostgreSQL adapter. Postgres claims a job with `FOR UPDATE SKIP LOCKED`, so several workers never take the same job. A job whose lease expires goes to another worker, so handlers must be idempotent. Both adapters pass the same conformance suite.

## Pipeline editor and git forge

The SPA edits `asac.yaml` at `/app/p/<project>/pipeline/edit`. Changes are saved as a draft in the portal. Nothing reaches git until someone proposes the draft: the portal then creates the branch `asac/pipeline-<id>`, commits the file and opens a change request (pull request or merge request). It never pushes to the default branch. If the default branch changed the same file since the draft was based on it, the proposal is refused and the upstream diff is shown. A merged change request marks the draft as applied the next time the draft is opened.

Who can edit: project owner, developer, product owner and organisation admin. Only the author of a draft can save or propose it. Anyone who can see the project can read its drafts.

### Forge variables

Set these in the project's Variables page (stored in `asac.vars.yaml`).

| Key | Value |
|---|---|
| `forge_kind` | `git`, `github`, `gitlab`, `gitea`, `forgejo`, `bitbucket` or `azure_devops`. `git` reads the repository but cannot open change requests |
| `forge_repo` | `git`: path or URL of the repository. `github`: `owner/name`. `gitlab`: project path or id. `gitea`/`forgejo`: `owner/name`. `bitbucket`: `workspace/slug`. `azure_devops`: `organization/project/repository` |
| `forge_api` | API base URL. Optional for self-hosted GitHub Enterprise, GitLab, Bitbucket and Azure DevOps Server; required for Gitea and Forgejo (`https://host/api/v1`). Must be `https://` |
| `forge_token` | Vault reference only, for example `${vault.forge/token}`. Needs write access to branches and change requests |

The portal resolves the vault reference from the environment variable `ASAC_VAULT_<PATH>` (path upper-cased, every character that is not a letter or digit becomes `_`). For `${vault.forge/token}` that is `ASAC_VAULT_FORGE_TOKEN`. Without `forge_kind` the editor answers that no forge is configured.

## Ticket and wiki links

A run started from a ticket shows "Trigger: PAY-139 in Jira" on the run page and in the decision room. The link is built without a network call; the ticket title and status are read from the tracker when it answers and are left out when it does not, so a tracker outage never breaks the page. Without a tracker configured the trigger is shown as plain text.

`GET /api/v1/projects/<project>/wiki/pages?q=<text>` searches the project wiki by page title (10 results at most). It needs project visibility and answers 409 when no wiki is configured.

### Tracker and wiki variables

| Key | Value |
|---|---|
| `tracker_kind` | `jira`, `github` or `gitlab` |
| `tracker_url` | Jira: base URL, for example `https://acme.atlassian.net`. GitHub or GitLab: optional API URL for self-hosted instances. Must be `https://` |
| `tracker_project` | GitHub: `owner/name`. GitLab: project path. Not used by Jira |
| `tracker_user` | Jira Cloud only: account email (Basic auth with an API token). Leave empty for Jira Data Center (personal access token) |
| `tracker_token` | Vault reference. Read access to issues is enough |
| `wiki_kind` | `confluence` or `gitlab`. GitHub wikis have no API and are not supported |
| `wiki_url` | Confluence: base URL including `/wiki` on Cloud. GitLab: optional API URL. Must be `https://` |
| `wiki_space` | Confluence space key, for example `PAY` |
| `wiki_project` | GitLab project path |
| `wiki_user` | Confluence Cloud only: account email |
| `wiki_token` | Vault reference. Read access is enough |

Tokens are resolved the same way as `forge_token`. Error messages name the vault reference, never its value.

## Deliverables and spend

Every run keeps its files in an `ArtifactStore` (filesystem adapter: `<state_dir>/artifacts/<run>/<name>` plus an append-only `index.jsonl`). Files are immutable, limited to 10 MiB, and named `^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$`. When a delegated step runs in the runner, its full output is stored as `<step>-output.txt`.

`GET /api/v1/projects/{pid}/runs/{run_id}` returns `artifacts` (name, step, size, sha256, time) and `spend` (`tokens`, `cost_usd`, summed from `spend.recorded` audit rows). `GET .../runs/{run_id}/artifacts/{name}` downloads an indexed file only, with `Content-Disposition: attachment` and `X-Content-Type-Options: nosniff`. Unknown or unsafe names return 404.

The run page shows tokens and cost in its header, a Deliverables tab (download links) and a Hooks tab (result and output of each hook).
