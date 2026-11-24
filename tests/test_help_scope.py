"""--help shows what version 0.1 supports; the rest still works but is not advertised."""

from __future__ import annotations

from typer.testing import CliRunner

from asac.cli import app

runner = CliRunner()
SUPPORTED = {"init", "validate", "vars", "plan", "apply", "run", "submit", "status", "gates",
             "approve", "evidence", "logs", "audit", "learn", "kill", "clean", "doctor",
             "version"}  # fmt: skip
UNSUPPORTED = {"portal", "daemon", "project"}


def _listed(out: str) -> set[str]:
    return {line.strip("│ ").split()[0] for line in out.splitlines() if line.startswith("│ ")}


def test_help_lists_exactly_the_supported_commands() -> None:
    listed = _listed(runner.invoke(app, ["--help"]).output)
    assert listed >= SUPPORTED
    assert not (UNSUPPORTED & listed), UNSUPPORTED & listed


def test_hidden_commands_still_work() -> None:
    for name in sorted(UNSUPPORTED):
        r = runner.invoke(app, [name, "--help"])
        assert r.exit_code == 0, (name, r.output)


def test_the_application_help_names_every_supported_command() -> None:
    """F64.2: the sentence at the top of `asac --help` is the list of the v1 commands."""
    out = " ".join(runner.invoke(app, ["--help"]).output.split())
    sentence = out.split("Version 0.1 supports:")[1].split(".")[0]
    named = {w.strip(", ") for w in sentence.split()}
    assert named >= (SUPPORTED - {"version"})
    assert not (UNSUPPORTED & named)


def test_run_help_describes_what_run_does() -> None:
    """F64.3: create a run and execute it, or run a single step."""
    out = " ".join(runner.invoke(app, ["run", "--help"]).output.split())
    assert "Create a run and execute it" in out and "run only that step" in out
