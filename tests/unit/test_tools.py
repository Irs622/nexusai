"""
Unit tests for Tool System, Tool Registry, TerminalTool, and ExecuteToolCommandHandler.
"""

from unittest.mock import AsyncMock, patch

import pytest
from pydantic import BaseModel, Field

from nexusai.bus.bus import EventBus
from nexusai.bus.commands import ExecuteToolCommand, ExecuteToolCommandHandler
from nexusai.bus.events import ToolExecutedEvent
from nexusai.core.config import SecuritySettings
from nexusai.core.errors import SecurityError, ToolExecutionError
from nexusai.security.guard import RiskLevel, SecurityGuard
from nexusai.tools.base import BaseTool
from nexusai.tools.registry import ToolRegistry
from nexusai.tools.system.terminal import TerminalTool


class DummyInputSchema(BaseModel):
    query: str = Field(..., description="Sample search query")


class DummyTool(BaseTool):
    name = "dummy_tool"
    description = "Dummy test tool"
    risk_level = RiskLevel.LOW
    input_schema = DummyInputSchema

    async def execute(self, query: str, **kwargs: object) -> str:
        return f"Processed: {query}"


@pytest.fixture
def registry() -> ToolRegistry:
    reg = ToolRegistry()
    reg.register(DummyTool())
    reg.register(TerminalTool())
    return reg


@pytest.fixture
def security_guard() -> SecurityGuard:
    settings = SecuritySettings(
        strict_mode=True,
        auto_approve_low_risk=True,
        forbidden_commands=["rm -rf /", "sudo rm -rf"],
        protected_paths=["/System", "/etc"],
    )
    return SecurityGuard(settings)


@pytest.fixture
def event_bus() -> EventBus:
    return EventBus()


def test_tool_registry_registration_and_schemas(registry: ToolRegistry) -> None:
    assert registry.has_tool("dummy_tool") is True
    assert registry.has_tool("execute_terminal") is True

    tool = registry.get("dummy_tool")
    assert tool.name == "dummy_tool"

    schemas = registry.get_all_schemas()
    assert len(schemas) == 2

    dummy_schema = next(s for s in schemas if s["function"]["name"] == "dummy_tool")
    assert dummy_schema["type"] == "function"
    assert dummy_schema["function"]["description"] == "Dummy test tool"
    assert "query" in dummy_schema["function"]["parameters"]["properties"]


@pytest.mark.asyncio
async def test_terminal_tool_execution() -> None:
    tool = TerminalTool()
    mock_process = AsyncMock()
    mock_process.communicate.return_value = (b"hello world\n", b"")
    mock_process.returncode = 0

    with patch("asyncio.create_subprocess_shell", return_value=mock_process) as mock_shell:
        result = await tool.execute(command="echo 'hello world'")
        import sys

        expected_kwargs = {
            "stdout": -1,  # asyncio.subprocess.PIPE
            "stderr": -1,
        }
        if sys.platform != "win32":
            expected_kwargs["start_new_session"] = True

        mock_shell.assert_called_once_with(
            "echo 'hello world'",
            **expected_kwargs,
        )
        assert result["stdout"] == "hello world\n"
        assert result["stderr"] == ""
        assert result["returncode"] == 0


@pytest.mark.asyncio
async def test_execute_tool_command_low_risk_success(
    registry: ToolRegistry,
    security_guard: SecurityGuard,
    event_bus: EventBus,
) -> None:
    handler = ExecuteToolCommandHandler(registry, security_guard, event_bus)

    published_events: list[ToolExecutedEvent] = []

    async def on_tool_executed(event: ToolExecutedEvent) -> None:
        published_events.append(event)

    event_bus.subscribe(ToolExecutedEvent, on_tool_executed)

    cmd = ExecuteToolCommand(
        tool_name="dummy_tool",
        arguments={"query": "nexus_test"},
    )

    result = await handler(cmd)
    assert result == "Processed: nexus_test"
    assert len(published_events) == 1
    assert published_events[0].tool_name == "dummy_tool"
    assert published_events[0].success is True


@pytest.mark.asyncio
async def test_execute_tool_command_high_risk_unconfirmed_blocked(
    registry: ToolRegistry,
    security_guard: SecurityGuard,
    event_bus: EventBus,
) -> None:
    handler = ExecuteToolCommandHandler(registry, security_guard, event_bus)

    cmd = ExecuteToolCommand(
        tool_name="execute_terminal",
        arguments={"command": "ls -la"},
        user_confirmed=False,
    )

    with pytest.raises(SecurityError) as exc_info:
        await handler(cmd)

    assert "Security policy denied" in str(exc_info.value)


@pytest.mark.asyncio
async def test_execute_tool_command_forbidden_pattern_blocked(
    registry: ToolRegistry,
    security_guard: SecurityGuard,
    event_bus: EventBus,
) -> None:
    handler = ExecuteToolCommandHandler(registry, security_guard, event_bus)

    cmd = ExecuteToolCommand(
        tool_name="execute_terminal",
        arguments={"command": "rm -rf /"},
        user_confirmed=True,
    )

    with pytest.raises(SecurityError) as exc_info:
        await handler(cmd)

    assert "forbidden pattern" in str(exc_info.value)


@pytest.mark.asyncio
async def test_execute_tool_command_high_risk_confirmed_success(
    registry: ToolRegistry,
    security_guard: SecurityGuard,
    event_bus: EventBus,
) -> None:
    handler = ExecuteToolCommandHandler(registry, security_guard, event_bus)

    mock_process = AsyncMock()
    mock_process.communicate.return_value = (b"file.txt\n", b"")
    mock_process.returncode = 0

    cmd = ExecuteToolCommand(
        tool_name="execute_terminal",
        arguments={"command": "ls"},
        user_confirmed=True,
    )

    with patch("asyncio.create_subprocess_shell", return_value=mock_process):
        result = await handler(cmd)
        assert result["stdout"] == "file.txt\n"
        assert result["returncode"] == 0


@pytest.mark.asyncio
async def test_execute_tool_command_invalid_args(
    registry: ToolRegistry,
    security_guard: SecurityGuard,
    event_bus: EventBus,
) -> None:
    handler = ExecuteToolCommandHandler(registry, security_guard, event_bus)

    cmd = ExecuteToolCommand(
        tool_name="dummy_tool",
        arguments={},  # Missing required 'query' parameter
    )

    with pytest.raises(ToolExecutionError) as exc_info:
        await handler(cmd)

    assert "Invalid arguments" in str(exc_info.value)
