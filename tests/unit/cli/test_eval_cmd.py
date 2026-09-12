"""
Unit tests for Typer CLI eval command suite.
"""

from typer.testing import CliRunner

from nexusai.cli.app import app

runner = CliRunner()


def test_cli_eval_help() -> None:
    """Check nexusai eval --help outputs subcommand info."""
    result = runner.invoke(app, ["eval", "--help"])
    assert result.exit_code == 0
    assert "Agent runtime evaluation" in result.output
    assert "run" in result.output


def test_cli_eval_run_help() -> None:
    """Check nexusai eval run --help displays all arguments and flags."""
    result = runner.invoke(app, ["eval", "run", "--help"])
    assert result.exit_code == 0
    assert "--suite" in result.output
    assert "--baseline" in result.output
    assert "--record-baseline" in result.output
    assert "--safety-only" in result.output
    assert "--format" in result.output
    assert "--output" in result.output
    assert "--threshold" in result.output


def test_cli_eval_run_default() -> None:
    """Run nexusai eval run with default arguments against v1.0 baseline."""
    result = runner.invoke(app, ["eval", "run"])
    assert result.exit_code == 0
    assert "NEXUSAI AGENT RUNTIME EVALUATION REPORT" in result.output
    assert "PASSED" in result.output


def test_cli_eval_run_json_format() -> None:
    """Run nexusai eval run with --format json."""
    result = runner.invoke(app, ["eval", "run", "--format", "json"])
    assert result.exit_code == 0
    assert '"metrics":' in result.output
    assert '"task_success_rate":' in result.output
