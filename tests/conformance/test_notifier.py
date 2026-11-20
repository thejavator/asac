"""Conformance for the Notifier port: every adapter delivers, and fails without leaking."""

from __future__ import annotations

import json
import smtplib
from collections.abc import Callable
from email.message import EmailMessage
from typing import Any

import httpx
import pytest

from asac.adapters.notify import (
    FanOut,
    SlackNotifier,
    SmtpNotifier,
    TeamsNotifier,
    WebhookNotifier,
    from_env,
    from_spec,
)
from asac.ports.notifier import Notification, Notifier, NotifyError

URL = "https://hooks.example/secret-token-123"
NOTE = Notification(
    "gate.opened", "Decision needed: gate_r1_requirements", "Step requirements waits.",
    "r1", "requirements", "gate_r1_requirements", "product_owner",
)  # fmt: skip


class Http:
    def __init__(self, status: int = 200) -> None:
        self.requests: list[httpx.Request] = []
        self.status = status
        self.client = httpx.Client(transport=httpx.MockTransport(self._handle))

    def _handle(self, req: httpx.Request) -> httpx.Response:
        self.requests.append(req)
        if self.status == -1:
            raise httpx.ConnectError("boom", request=req)
        return httpx.Response(self.status)


class FakeSmtp:
    sent: list[EmailMessage] = []
    fail = False

    def __enter__(self) -> FakeSmtp:
        return self

    def __exit__(self, *a: object) -> None:
        return None

    def login(self, u: str, p: str) -> None:
        self.logged = (u, p)

    def send_message(self, m: EmailMessage) -> None:
        if FakeSmtp.fail:
            raise smtplib.SMTPServerDisconnected("down")
        FakeSmtp.sent.append(m)


def make(kind: str, http: Http) -> Notifier:
    if kind == "webhook":
        return WebhookNotifier(URL, "s3cret", http.client)
    if kind == "slack":
        return SlackNotifier(URL, http.client)
    if kind == "teams":
        return TeamsNotifier(URL, http.client)
    raise AssertionError(kind)


@pytest.fixture(params=["webhook", "slack", "teams"])
def kind(request: pytest.FixtureRequest) -> str:
    return str(request.param)


def test_delivers_a_post_with_the_title(kind: str) -> None:
    http = Http()
    make(kind, http).send(NOTE)
    (req,) = http.requests
    assert req.method == "POST" and str(req.url) == URL
    assert "gate_r1_requirements" in req.content.decode()


@pytest.mark.parametrize("status", [500, 404, -1])
def test_failure_raises_without_leaking_the_url(kind: str, status: int) -> None:
    with pytest.raises(NotifyError) as err:
        make(kind, Http(status)).send(NOTE)
    assert "secret-token-123" not in str(err.value) and "hooks.example" not in str(err.value)


def test_webhook_signature_is_verifiable() -> None:
    import hashlib
    import hmac

    http = Http()
    WebhookNotifier(URL, "s3cret", http.client).send(NOTE)
    req = http.requests[0]
    mac = hmac.new(b"s3cret", req.content, hashlib.sha256).hexdigest()
    assert req.headers["X-ASAC-Signature"] == f"sha256={mac}"
    assert json.loads(req.content)["gate_id"] == "gate_r1_requirements"


def test_webhook_without_secret_is_unsigned() -> None:
    http = Http()
    WebhookNotifier(URL, None, http.client).send(NOTE)
    assert "X-ASAC-Signature" not in http.requests[0].headers


def test_slack_and_teams_payload_shapes() -> None:
    h1, h2 = Http(), Http()
    SlackNotifier(URL, h1.client).send(NOTE)
    TeamsNotifier(URL, h2.client).send(NOTE)
    assert "text" in json.loads(h1.requests[0].content)
    assert json.loads(h2.requests[0].content)["attachments"][0]["content"]["type"] == "AdaptiveCard"


def smtp(**kw: Any) -> SmtpNotifier:
    FakeSmtp.sent, FakeSmtp.fail = [], False
    return SmtpNotifier(
        "mail", 587, "asac@x", ["po@x", "qa@x"], factory=lambda: FakeSmtp(),  # type: ignore[arg-type,return-value]
        **kw,
    )  # fmt: skip


def test_smtp_sends_one_message_to_all_recipients() -> None:
    smtp(user="u", password="p").send(NOTE)
    (m,) = FakeSmtp.sent
    assert m["To"] == "po@x, qa@x" and m["Subject"] == NOTE.title
    assert "product_owner" in m.get_content()


def test_smtp_failure_is_a_notify_error() -> None:
    n = smtp()
    FakeSmtp.fail = True
    with pytest.raises(NotifyError, match="mail delivery failed"):
        n.send(NOTE)


def test_fanout_continues_after_a_failing_target() -> None:
    good, bad = Http(), Http(500)
    fan = FanOut([make("slack", bad), make("teams", good)])
    with pytest.raises(NotifyError):
        fan.send(NOTE)
    assert len(good.requests) == 1  # the second target still got it


@pytest.mark.parametrize(
    "spec",
    ["slack+ftp://x", "carrier-pigeon", "smtp://host", "smtp://host?to=", "webhook+"],
)
def test_bad_specs_are_refused(spec: str) -> None:
    with pytest.raises(NotifyError):
        from_spec(spec)


def test_specs_build_the_right_adapters() -> None:
    assert isinstance(from_spec("slack+https://x"), SlackNotifier)
    assert isinstance(from_spec("teams+https://x"), TeamsNotifier)
    assert isinstance(from_spec("webhook+https://x", "s"), WebhookNotifier)
    assert isinstance(from_spec("smtps://u:p%40@h:465?to=a@x&from=b@x"), SmtpNotifier)


def test_from_env() -> None:
    assert from_env({}) is None
    assert isinstance(from_env({"ASAC_NOTIFY": "slack+https://x, teams+https://y"}), FanOut)


_ = Callable
