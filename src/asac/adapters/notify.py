"""Notifier adapters: generic webhook, Slack, Teams, SMTP, and a fan-out.

Configuration is one string per target in ``ASAC_NOTIFY`` (comma separated):

    webhook+https://hooks.example/asac        signed with ASAC_WEBHOOK_SECRET when set
    slack+https://hooks.slack.com/services/…  Slack incoming webhook
    teams+https://…                           Teams workflow / incoming webhook
    smtp://user:pass@host:587?to=a@x,b@x&from=asac@x   STARTTLS; smtps:// for implicit TLS

Errors never include the URL: webhook URLs are secrets.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import smtplib
import ssl
from collections.abc import Callable, Mapping
from email.message import EmailMessage
from urllib.parse import parse_qs, unquote, urlparse

import httpx

from asac.ports.notifier import Notification, Notifier, NotifyError


def _post(
    http: httpx.Client, url: str, payload: Mapping[str, object], headers: dict[str, str]
) -> None:
    try:
        resp = http.post(url, content=json.dumps(payload), headers=headers)
    except httpx.HTTPError as exc:
        raise NotifyError(f"delivery failed: {type(exc).__name__}") from None
    if resp.status_code >= 300:
        raise NotifyError(f"target answered HTTP {resp.status_code}")


def _text(n: Notification) -> str:
    lines = [f"{n.title}", n.body]
    if n.role:
        lines.append(f"Role needed: {n.role}")
    if n.link:
        lines.append(n.link)
    return "\n".join(x for x in lines if x)


class WebhookNotifier:
    def __init__(
        self, url: str, secret: str | None = None, http: httpx.Client | None = None
    ) -> None:
        self._url, self._secret = url, secret
        self._http = http or httpx.Client(timeout=10)

    def send(self, note: Notification) -> None:
        body = json.dumps(note.__dict__, sort_keys=True)
        headers = {"Content-Type": "application/json"}
        if self._secret:
            mac = hmac.new(self._secret.encode(), body.encode(), hashlib.sha256).hexdigest()
            headers["X-ASAC-Signature"] = f"sha256={mac}"
        try:
            resp = self._http.post(self._url, content=body, headers=headers)
        except httpx.HTTPError as exc:
            raise NotifyError(f"delivery failed: {type(exc).__name__}") from None
        if resp.status_code >= 300:
            raise NotifyError(f"target answered HTTP {resp.status_code}")


class SlackNotifier:
    def __init__(self, url: str, http: httpx.Client | None = None) -> None:
        self._url = url
        self._http = http or httpx.Client(timeout=10)

    def send(self, note: Notification) -> None:
        payload = {"text": f"*{note.title}*\n{_text(note).split(chr(10), 1)[-1]}"}
        _post(self._http, self._url, payload, {"Content-Type": "application/json"})


class TeamsNotifier:
    """Adaptive Card message, accepted by Teams workflow webhooks."""

    def __init__(self, url: str, http: httpx.Client | None = None) -> None:
        self._url = url
        self._http = http or httpx.Client(timeout=10)

    def send(self, note: Notification) -> None:
        card = {
            "type": "AdaptiveCard",
            "version": "1.4",
            "body": [
                {"type": "TextBlock", "text": note.title, "weight": "Bolder", "wrap": True},
                {"type": "TextBlock", "text": _text(note).split("\n", 1)[-1], "wrap": True},
            ],
        }
        payload = {
            "type": "message",
            "attachments": [
                {"contentType": "application/vnd.microsoft.card.adaptive", "content": card}
            ],
        }
        _post(self._http, self._url, payload, {"Content-Type": "application/json"})


class SmtpNotifier:
    def __init__(
        self,
        host: str,
        port: int,
        sender: str,
        to: list[str],
        user: str | None = None,
        password: str | None = None,
        implicit_tls: bool = False,
        factory: Callable[[], smtplib.SMTP] | None = None,
    ) -> None:
        self._args = (host, port, sender, to, user, password, implicit_tls)
        self._factory = factory

    def _connect(self) -> smtplib.SMTP:
        if self._factory is not None:
            return self._factory()
        host, port, _s, _t, _u, _p, tls = self._args
        if tls:
            return smtplib.SMTP_SSL(host, port, timeout=10, context=ssl.create_default_context())
        smtp = smtplib.SMTP(host, port, timeout=10)
        smtp.starttls(context=ssl.create_default_context())
        return smtp

    def send(self, note: Notification) -> None:
        _, _, sender, to, user, password, _ = self._args
        msg = EmailMessage()
        msg["Subject"] = note.title
        msg["From"] = sender
        msg["To"] = ", ".join(to)
        msg.set_content(_text(note))
        try:
            with self._connect() as smtp:
                if user and password:
                    smtp.login(user, password)
                smtp.send_message(msg)
        except (smtplib.SMTPException, OSError) as exc:
            raise NotifyError(f"mail delivery failed: {type(exc).__name__}") from None


class FanOut:
    """Send to every target; one failing target does not stop the others."""

    def __init__(self, targets: list[Notifier]) -> None:
        self._targets = targets

    def send(self, note: Notification) -> None:
        failures: list[str] = []
        for t in self._targets:
            try:
                t.send(note)
            except NotifyError as exc:
                failures.append(str(exc))
        if failures:
            raise NotifyError("; ".join(failures))


def from_spec(spec: str, secret: str | None = None) -> Notifier:
    """Build one notifier from a configuration string (see module docstring)."""
    scheme, sep, rest = spec.partition("+")
    if sep and scheme in ("webhook", "slack", "teams"):
        if not rest.startswith(("https://", "http://")):
            raise NotifyError(f"'{scheme}' target must be an http(s) URL")
        if scheme == "slack":
            return SlackNotifier(rest)
        if scheme == "teams":
            return TeamsNotifier(rest)
        return WebhookNotifier(rest, secret)
    if spec.startswith(("smtp://", "smtps://")):
        u = urlparse(spec)
        q = parse_qs(u.query)
        to = [a for v in q.get("to", []) for a in v.split(",") if a]
        if not u.hostname or not to:
            raise NotifyError("smtp target needs a host and ?to=")
        tls = u.scheme == "smtps"
        return SmtpNotifier(
            u.hostname,
            u.port or (465 if tls else 587),
            q.get("from", ["asac@localhost"])[0],
            to,
            unquote(u.username) if u.username else None,
            unquote(u.password) if u.password else None,
            tls,
        )
    raise NotifyError("unknown notification target (use webhook+, slack+, teams+ or smtp://)")


def from_env(env: dict[str, str]) -> Notifier | None:
    raw = env.get("ASAC_NOTIFY", "").strip()
    if not raw:
        return None
    secret = env.get("ASAC_WEBHOOK_SECRET")
    return FanOut([from_spec(s.strip(), secret) for s in raw.split(",") if s.strip()])


def from_project(values: dict[str, object], env: dict[str, str]) -> Notifier | None:
    """Targets of ``ASAC_NOTIFY`` plus the project's ``notify_targets``.

    ``notify_targets`` is a list of vault references; each one resolves to a target string
    (``slack+https://...``). A plain URL is refused: webhook URLs are secrets and must not sit
    in ``asac.vars.yaml``. A reference that cannot be resolved is skipped, never fatal.
    """
    from asac.adapters.vault import VaultError, resolve_vault

    secret = env.get("ASAC_WEBHOOK_SECRET")
    targets: list[Notifier] = []
    base = from_env(env)
    if base is not None:
        targets.append(base)
    raw = values.get("notify_targets") or []
    refs = raw if isinstance(raw, list) else [raw]
    for ref in refs:
        try:
            targets.append(from_spec(resolve_vault(str(ref), "a notification target"), secret))
        except (VaultError, NotifyError):
            continue  # best effort: a missing secret must not stop a run
    return FanOut(targets) if targets else None
