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


class SequentialToolCallProvider(BaseModelProvider):
    def __init__(self, responses: list[dict]) -> None:
        self.responses = responses
        self.call_count = 0
        self.last_messages: list[dict] = []

    async def chat(self, messages: list, tools: list | None = None) -> dict:
        self.last_messages = messages
        resp = self.responses[min(self.call_count, len(self.responses) - 1)]
        self.call_count += 1
        return resp


@pytest.mark.asyncio
async def test_start_chat_session_executes_tool_with_identity() -> None:
    """Verify tool execution succeeds in CLI chat because ambient identity is established."""
    from nexusai.security.identity import TenantContext

    prev_identity = TenantContext.get_current_identity()

    captured_identities: list[object] = []
    inputs = iter(["analyze workspace", "exit"])

    def custom_input() -> str:
        captured_identities.append(TenantContext.get_current_identity())
        return next(inputs)

    responses = [
        {
            "type": "tool_call",
            "tool_name": "workspace_list_directory",
            "arguments": {"path": "."},
        },
        {"type": "text", "content": "Here is the project analysis."},
    ]
    mock_provider = SequentialToolCallProvider(responses)

    await start_chat_session(
        session_id="test_cli_tool_exec",
        custom_input=custom_input,
        model_provider_override=mock_provider,
    )

    # Ambient identity was established during the loop with CLI metadata
    assert len(captured_identities) >= 1
    active_identity = captured_identities[0]
    assert active_identity is not None
    assert getattr(active_identity, "role", None) is not None
    assert getattr(active_identity, "metadata", {}).get("channel") == "cli"

    # After session finishes, ambient identity is cleanly restored
    assert TenantContext.get_current_identity() == prev_identity


@pytest.mark.asyncio
async def test_execute_tool_command_handler_approval_callback() -> None:
    """Verify ExecuteToolCommandHandler prompts approval callback and creates token for HIGH-risk tools."""
    from pydantic import BaseModel, Field

    from nexusai.bus.bus import EventBus
    from nexusai.bus.commands import ExecuteToolCommand, ExecuteToolCommandHandler
    from nexusai.core.config import SecuritySettings
    from nexusai.core.errors import SecurityError
    from nexusai.security.guard import RiskLevel, SecurityGuard
    from nexusai.security.identity import Identity, Role, TenantContext
    from nexusai.tools.base import BaseTool
    from nexusai.tools.registry import ToolRegistry

    class DangerSchema(BaseModel):
        cmd: str = Field(default="echo test")

    class DangerTool(BaseTool):
        name = "danger_tool"
        description = "Dangerous test tool"
        risk_level = RiskLevel.HIGH
        input_schema = DangerSchema

        async def execute(self, cmd: str = "echo test", **kwargs: object) -> str:
            return f"Executed {cmd}"

    registry = ToolRegistry()
    registry.register(DangerTool())
    guard = SecurityGuard(SecuritySettings(strict_mode=True))
    event_bus = EventBus()

    test_identity = Identity(tenant_id="default", user_id="test-op", role=Role.ADMIN)
    TenantContext.set_current_identity(test_identity)

    try:
        # Case 1: Operator Approves -> Tool executes
        approved_calls: list[tuple[str, dict, RiskLevel]] = []

        async def approve_cb(tool_name: str, args: dict, risk: RiskLevel) -> bool:
            approved_calls.append((tool_name, args, risk))
            return True

        handler_approved = ExecuteToolCommandHandler(
            registry, guard, event_bus, approval_callback=approve_cb
        )
        cmd = ExecuteToolCommand(
            tool_name="danger_tool",
            arguments={"cmd": "reboot"},
            user_id="test-op",
            tenant_id="default",
        )
        res = await handler_approved(cmd)
        assert res == "Executed reboot"
        assert len(approved_calls) == 1
        assert approved_calls[0][0] == "danger_tool"

        # Case 2: Operator Denies -> Tool execution blocked with SecurityError
        denied_calls: list[tuple[str, dict, RiskLevel]] = []

        async def deny_cb(tool_name: str, args: dict, risk: RiskLevel) -> bool:
            denied_calls.append((tool_name, args, risk))
            return False

        handler_denied = ExecuteToolCommandHandler(
            registry, guard, event_bus, approval_callback=deny_cb
        )
        with pytest.raises(SecurityError) as exc_info:
            await handler_denied(cmd)
        assert "Security policy denied" in str(exc_info.value)
        assert len(denied_calls) == 1
    finally:
        TenantContext.set_current_identity(None)


@pytest.mark.asyncio
async def test_start_chat_session_closes_memory(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify SQLiteMemory is cleanly closed when chat session terminates."""
    from unittest.mock import AsyncMock

    from nexusai.memory.sqlite_memory import SQLiteMemory

    mock_close = AsyncMock()
    monkeypatch.setattr(SQLiteMemory, "close", mock_close)

    inputs = iter(["exit"])

    def custom_input() -> str:
        return next(inputs)

    mock_provider = MockModelProvider()
    await start_chat_session(
        session_id="test_cli_close_session",
        custom_input=custom_input,
        model_provider_override=mock_provider,
    )

    mock_close.assert_awaited_once()
