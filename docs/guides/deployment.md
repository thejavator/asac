# Deploying the portal and the daemon

ASAC ships one container image. The same image runs the CLI, the portal (`asac portal`) and the webhook daemon (`asac daemon`). Nothing in it is tied to a vendor: identity is any standard OIDC provider, state is SQLite or Postgres, notifications are configured by URL.

## What you need

| Need | Choice |
|---|---|
| Identity | Any OIDC provider. Set `ASAC_OIDC_ISSUER`, `ASAC_OIDC_CLIENT_ID`, `ASAC_OIDC_REDIRECT_URI`, optionally `ASAC_OIDC_CLIENT_SECRET` and `ASAC_OIDC_ROLES_CLAIM`. |
| State | `ASAC_STATE_URL=postgresql://…` for a team. Without it, SQLite under `ASAC_STATE_DIR`. |
| Project files | `asac.yaml` and `.asac/` mounted at `/project`. |
| TLS | Terminated by your reverse proxy or ingress. The portal sets secure cookies and HSTS. |
| Webhooks | `ASAC_WEBHOOK_SECRET` for the HMAC check on `/webhooks/jira`. |
| Notifications | Optional `ASAC_NOTIFY`, see [Notifications](notifications.md). |

Both services answer `GET /healthz` for liveness and readiness probes. It returns no data.

## One VM with Docker Compose

```bash
cp .env.example .env     # fill in the values
docker compose up -d --build
```

`compose.yaml` starts Postgres, the portal and the daemon. Ports are bound to `127.0.0.1`: put your TLS proxy in front. Set `ASAC_PROJECT` to the directory that holds your `asac.yaml`, and `ASAC_PORTAL_PORT` / `ASAC_DAEMON_PORT` if the defaults (8080, 8090) are taken.

## Kubernetes or OpenShift

`deploy/kubernetes/asac.yaml` has a Secret, two Deployments, two Services and an Ingress. It sets no fixed user id, drops all capabilities and uses a read-only root filesystem for the portal, so it runs under OpenShift's restricted policy. On OpenShift, replace the Ingress with a Route.

Before applying:

1. Push the image to your registry and replace `ghcr.io/example/asac`.
2. Replace the Secret values (or create the Secret from your secret manager).
3. Create a PersistentVolumeClaim named `asac-project` holding the project files, or swap that volume for a git-sync sidecar.
4. Replace the host name `asac.example.com`.

The manifests are checked for well-formed YAML in the test suite but have not been applied to a live cluster in this repository's CI.

## Behind a reverse proxy

The portal rate-limits login by client address. Behind a proxy every request appears to come from the proxy, so limits are shared by all users. Keep the proxy's own rate limiting enabled until trusted-proxy support lands.
