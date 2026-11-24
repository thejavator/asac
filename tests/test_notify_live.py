"""Notifications sent to a real receiver, in another process, by a real run.

`tests/test_notifications.py` swaps the channel for a recorder. This file keeps the channel: a
run opens a gate, ASAC sends over a socket, and a separate process records what arrived. That is
what the stand-in cannot show: the bytes on the wire, the HMAC header, the Slack and Teams
bodies, a mail through SMTP, and a run that carries on when the target is down.

Local sockets only, no account, no money. Run with:

    ASAC_NOTIFY_LIVE=1 uv run pytest tests/test_notify_live.py -m integration -v
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from typer.testing import CliRunner

from asac.cli import app
from tests.conftest import init_git

pytestmark = [
    pytest.mark.integration,
    pytest.mark.enable_socket,  # the project blocks sockets by default; only these tests open any
    pytest.mark.skipif(
        os.environ.get("ASAC_NOTIFY_LIVE") != "1",
        reason="opens local sockets: set ASAC_NOTIFY_LIVE=1 to run it",
    ),
]

runner = CliRunner()

# A receiver that runs as its own process: an HTTP server and an SMTP server, each writing
# every request it gets to a file. It shares no memory with the test.
RECEIVER = r"""
import json, sys
from http.server import BaseHTTPRequestHandler, HTTPServer

out, http_port, smtp_port = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])

def record(entry):
    with open(out, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")

class Http(BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0))).decode()
        record({"kind": "http", "path": self.path, "headers": dict(self.headers), "body": body})
        self.send_response(204)
        self.end_headers()
    def log_message(self, *a):
        pass

HTTPServer(("127.0.0.1", http_port), Http).serve_forever()
"""

SMTP_RECEIVER = r"""
import json, socketserver, sys

out, port = sys.argv[1], int(sys.argv[2])

class Smtp(socketserver.StreamRequestHandler):
    def handle(self):
        w = lambda s: (self.wfile.write((s + "\r\n").encode()), self.wfile.flush())
        w("220 test")
        data, in_data = [], False
        for raw in self.rfile:
            line = raw.decode().rstrip("\r\n")
            if in_data:
                if line == ".":
                    in_data = False
                    with open(out, "a", encoding="utf-8") as f:
                        f.write(json.dumps({"kind": "smtp", "message": "\n".join(data)}) + "\n")
                    w("250 ok")
                else:
                    data.append(line)
                continue
            cmd = line.upper()
            if cmd.startswith("EHLO"):
                w("250 test")          # no STARTTLS offered: the plain test below sets smtp://
            elif cmd.startswith("DATA"):
                in_data = True
                w("354 go")
            elif cmd.startswith("QUIT"):
                w("221 bye")
                return
            else:
                w("250 ok")

socketserver.TCPServer.allow_reuse_address = True
socketserver.TCPServer(("127.0.0.1", port), Smtp).serve_forever()
"""


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _wait(port: int) -> None:
    for _ in range(100):
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return
        time.sleep(0.05)
    raise RuntimeError(f"receiver on port {port} did not start")


class Receiver:
    def __init__(self, log: Path, http_port: int, smtp_port: int) -> None:
        self.log, self.http_port, self.smtp_port = log, http_port, smtp_port

    def received(self) -> list[dict[str, object]]:
        if not self.log.exists():
            return []
        return [json.loads(line) for line in self.log.read_text().splitlines() if line]

    def wait_for(self, count: int, timeout: float = 10.0) -> list[dict[str, object]]:
        end = time.time() + timeout
        while time.time() < end:
            got = self.received()
            if len(got) >= count:
                return got
            time.sleep(0.05)
        return self.received()


@pytest.fixture
def receiver(tmp_path: Path) -> Iterator[Receiver]:
    log = tmp_path / "received.jsonl"
    http_port, smtp_port = _free_port(), _free_port()
    procs = [
        subprocess.Popen([sys.executable, "-I", "-c", RECEIVER, str(log), str(http_port), "0"]),
        subprocess.Popen([sys.executable, "-I", "-c", SMTP_RECEIVER, str(log), str(smtp_port)]),
    ]
    try:
        _wait(http_port)
        _wait(smtp_port)
        yield Receiver(log, http_port, smtp_port)
    finally:
        for p in procs:
            p.terminate()
            p.wait(timeout=5)


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "proj"
    root.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.delenv("ASAC_STATE_DIR", raising=False)
    monkeypatch.setenv("ASAC_FIXED_TIME", "2026-01-01T09:00:00Z")
    monkeypatch.setenv("ASAC_AUTORUN", "0")
    monkeypatch.setenv("ASAC_SANDBOX", "0")
    monkeypatch.delenv("ASAC_WEBHOOK_SECRET", raising=False)
    runner.invoke(app, ["init", str(root), "--template", "feature"])
    (root / "asac.vars.yaml").write_text("tool: claude-code\n")
    init_git(root)
    return root


def _open_a_gate(project: Path, run_id: str = "n1") -> None:
    """A real run: the requirements step waits for a person, then its gate opens."""
    f = str(project / "asac.yaml")
    r = runner.invoke(app, ["apply", "-p", "feature", "--harness", "claude-code",
                            "--run-id", run_id, "-f", f])  # fmt: skip
    assert r.exit_code == 2, r.output
    work = project / ".asac-state" / "worktrees" / run_id
    (work / "SPEC.md").write_text("# Spec\n## Acceptance criteria\n- it works\n")
    r = runner.invoke(app, ["submit", run_id, "--by", "dev", "-f", f])
    assert r.exit_code == 2 and f"gate_{run_id}_requirements" in r.output, r.output


def test_webhook_receives_a_signed_gate_notification(
    project: Path, receiver: Receiver, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ASAC_WEBHOOK_SECRET", "s3cret")
    monkeypatch.setenv("ASAC_NOTIFY", f"webhook+http://127.0.0.1:{receiver.http_port}/hook")
    _open_a_gate(project)
    (got,) = receiver.wait_for(1)
    body = json.loads(str(got["body"]))
    assert got["path"] == "/hook"
    assert body["kind"] == "gate.opened" and body["run_id"] == "n1"
    assert body["gate_id"] == "gate_n1_requirements" and body["role"] == "product_owner"
    headers = got["headers"]
    assert isinstance(headers, dict)
    expected = hmac.new(b"s3cret", str(got["body"]).encode(), hashlib.sha256).hexdigest()
    assert headers["X-ASAC-Signature"] == f"sha256={expected}"


def test_slack_and_teams_receive_their_own_body_shape(
    project: Path, receiver: Receiver, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = f"http://127.0.0.1:{receiver.http_port}"
    monkeypatch.setenv("ASAC_NOTIFY", f"slack+{base}/slack,teams+{base}/teams")
    _open_a_gate(project)
    got = {str(g["path"]): json.loads(str(g["body"])) for g in receiver.wait_for(2)}
    assert "Decision needed" in got["/slack"]["text"]
    card = got["/teams"]["attachments"][0]["content"]
    assert card["type"] == "AdaptiveCard" and "Decision needed" in card["body"][0]["text"]


def test_smtp_target_delivers_a_mail(
    project: Path, receiver: Receiver, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The receiver offers no STARTTLS, so the sender is built without it for this local check:
    # the SMTP wire format and the mail content are what is under test here.
    import smtplib

    from asac.adapters import notify

    original = notify.SmtpNotifier._connect
    monkeypatch.setattr(
        notify.SmtpNotifier,
        "_connect",
        lambda self: smtplib.SMTP("127.0.0.1", receiver.smtp_port, timeout=10),
    )
    monkeypatch.setenv(
        "ASAC_NOTIFY",
        f"smtp://127.0.0.1:{receiver.smtp_port}?to=po@example.com&from=asac@example.com",
    )
    _open_a_gate(project)
    (got,) = receiver.wait_for(1)
    message = str(got["message"])
    assert got["kind"] == "smtp"
    assert "To: po@example.com" in message and "From: asac@example.com" in message
    assert "Subject: Decision needed: gate_n1_requirements" in message
    assert original is not notify.SmtpNotifier._connect  # the real STARTTLS path is unit-tested


def test_an_unreachable_target_never_stops_the_run(
    project: Path, receiver: Receiver, monkeypatch: pytest.MonkeyPatch
) -> None:
    dead = _free_port()  # nothing listens here
    monkeypatch.setenv(
        "ASAC_NOTIFY",
        f"webhook+http://127.0.0.1:{dead}/x,webhook+http://127.0.0.1:{receiver.http_port}/ok",
    )
    _open_a_gate(project)  # the run still reaches its gate
    (got,) = receiver.wait_for(1)
    assert got["path"] == "/ok"  # the live target still got its message
    logs = runner.invoke(app, ["logs", "n1", "-f", str(project / "asac.yaml")]).output
    assert "notify.failed" in logs
    assert "gate.opened" in logs
    # F67.7: the audit names the kind of failure, never the target's address
    failed = next(line for line in logs.splitlines() if "notify.failed" in line)
    assert "delivery failed: ConnectError" in failed
    assert str(dead) not in failed and "127.0.0.1" not in failed and "/x" not in failed
