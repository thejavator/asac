"""--help shows what version 0.1 supports; the rest still works but is not advertised."""

from __future__ import annotations

from typer.testing import CliRunner

from asac.cli import app

runner = CliRunner()
SUPPORTED = {"validate", "plan", "apply", "status", "gates", "approve", "evidence", "logs",
             "audit", "kill", "clean", "doctor", "version"}  # fmt: skip
UNSUPPORTED = {"init", "run", "learn", "portal", "daemon", "vars", "project"}


def _listed(out: str) -> set[str]:
    return {line.strip("│ ").split()[0] for line in out.splitlines() if line.startswith("│ ")}


def test_help_lists_exactly_the_supported_commands() -> None:
    listed = _listed(runner.invoke(app, ["--help"]).output)
    assert listed >= SUPPORTED
    assert not (UNSUPPORTED & listed), UNSUPPORTED & listed


def test_hidden_commands_still_work() -> None:
    for name in ("init", "run", "learn", "portal", "daemon", "vars", "project"):
        r = runner.invoke(app, [name, "--help"])
        assert r.exit_code == 0, (name, r.output)
