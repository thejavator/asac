from typer.testing import CliRunner

from asac.cli import app


def test_version_command() -> None:
    result = CliRunner().invoke(app, ["version"])
    assert result.exit_code == 0
    assert "spec 0.4" in result.stdout
