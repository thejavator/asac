# Notifications

ASAC tells people when something needs them, so a gate does not wait unseen. Notification
is a replaceable port: choose the targets by configuration, with no code change.

## What is sent

| Event | When | Includes |
|---|---|---|
| `gate.opened` | A gate waits for a decision | gate id, role needed |
| `step.blocked` | A policy, budget or missing evidence stopped the run | reason |
| `step.escalated` | A step needs a person | reason |
| `step.failed` | A step failed | reason |

## Configure targets

Set `ASAC_NOTIFY` to one or more targets, separated by commas.

| Target | Format |
|---|---|
| Generic webhook | `webhook+https://hooks.example/asac` |
| Slack | `slack+https://hooks.slack.com/services/...` |
| Microsoft Teams | `teams+https://...` |
| E-mail | `smtp://user:pass@host:587?to=po@example.com,qa@example.com&from=asac@example.com` (`smtps://` for implicit TLS) |

```bash
export ASAC_NOTIFY="slack+https://hooks.slack.com/services/T000/B000/XXXX,smtp://mail.internal:587?to=po@example.com"
```

Webhook URLs are secrets. Keep them in your secret manager, not in the repository.

### Targets per project

`ASAC_NOTIFY` is global. A project can add its own targets with `notify_targets` in its
`asac.vars.yaml`: a list of vault references, each resolving to a target string in the
format above.

```yaml
notify_targets:
  - ${vault.notify/payments-slack}   # ASAC_VAULT_NOTIFY_PAYMENTS_SLACK=slack+https://hooks...
```

A plain URL in the vars file is ignored, because the URL is a secret. A reference that cannot
be resolved is skipped and never stops a run. Targets of the project and `ASAC_NOTIFY` both
receive the event.

## In the interface

The portal shows the number of gates waiting for you in the navigation (Decision Room) and in
the browser tab title, refreshed every 30 seconds.

## Guarantees

- **Best effort.** A failing channel never fails or blocks a run. The failure is recorded
  in the audit trail as `notify.failed`.
- **No leaks.** Error messages and audit entries never contain the target URL.
- **Signed webhooks.** With `ASAC_WEBHOOK_SECRET` set, the generic webhook carries an
  `X-ASAC-Signature: sha256=<hmac>` header over the exact request body.
- **Fan-out.** One broken target does not stop delivery to the others.

## Write your own adapter

Implement `asac.ports.notifier.Notifier` (one method, `send(note)`), raise `NotifyError`
on failure, and run it against `tests/conformance/test_notifier.py`.
