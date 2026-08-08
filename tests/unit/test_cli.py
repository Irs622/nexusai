"""
Unit tests for Typer CLI Application.
"""

from typer.testing import CliRunner

from nexusai.cli.app import app

runner = CliRunner()


def test_cli_help() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "NexusAI" in result.output


def test_cli_status() -> None:
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    assert "System Status: OPERATIONAL" in result.output
    assert "Environment:" in result.output
