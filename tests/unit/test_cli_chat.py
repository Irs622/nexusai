"""
Unit tests for CLI Interactive Chat Session.
"""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from nexusai.cli.app import app
from nexusai.cli.chat import start_chat_session
from nexusai.models.base import BaseModelProvider

runner = CliRunner()


class MockModelProvider(BaseModelProvider):
    async def chat(self, messages: list, tools: list | None = None) -> dict:
        return {"type": "text", "content": "NexusAI Online"}


@pytest.mark.asyncio
async def test_start_chat_session_graceful_exit() -> None:
    inputs = iter(["hello", "exit"])

    def custom_input() -> str:
        return next(inputs)

    mock_provider = MockModelProvider()
    await start_chat_session(
        session_id="test_cli_session",
        custom_input=custom_input,
        model_provider_override=mock_provider,
    )


@pytest.mark.asyncio
async def test_start_chat_session_keyboard_interrupt() -> None:
    def custom_input() -> str:
        raise KeyboardInterrupt()

    mock_provider = MockModelProvider()
    await start_chat_session(
        session_id="test_cli_session",
        custom_input=custom_input,
        model_provider_override=mock_provider,
    )


def test_cli_chat_command_help() -> None:
    result = runner.invoke(app, ["chat", "--help"])
    assert result.exit_code == 0
    assert "NexusAI" in result.output
