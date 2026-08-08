"""
Unit tests for Model Providers, Prompt Builder, Brain Coordinator, and Context Engine Integration.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel, Field

from nexusai.brain.coordinator import BrainCoordinator
from nexusai.brain.prompt import PromptBuilder
from nexusai.bus.bus import CommandBus, EventBus
from nexusai.bus.commands import ExecuteToolCommand, ExecuteToolCommandHandler
from nexusai.context.engine import WorkingContext
from nexusai.core.config import SecuritySettings
from nexusai.core.errors import ConfigurationError
from nexusai.models.base import BaseModelProvider
from nexusai.models.openai_provider import OpenAIProvider
from nexusai.security.guard import RiskLevel, SecurityGuard
from nexusai.tools.base import BaseTool
from nexusai.tools.registry import ToolRegistry


class SampleInputSchema(BaseModel):
    app_name: str = Field(..., description="App name")


class SampleAppTool(BaseTool):
    name = "open_app"
    description = "Opens an application"
    risk_level = RiskLevel.LOW
    input_schema = SampleInputSchema

    async def execute(self, app_name: str, **kwargs: object) -> str:
        return f"Opened {app_name}"


class MockModelProvider(BaseModelProvider):
    def __init__(self, response: dict | list[dict]) -> None:
        self.responses = response if isinstance(response, list) else [response]
        self.call_count = 0
        self.last_messages: list = []
        self.last_tools: list | None = None

    async def chat(self, messages: list, tools: list | None = None) -> dict:
        self.last_messages = messages
        self.last_tools = tools
        resp = self.responses[min(self.call_count, len(self.responses) - 1)]
        self.call_count += 1
        return resp


@pytest.fixture
def registry() -> ToolRegistry:
    reg = ToolRegistry()
    reg.register(SampleAppTool())
    return reg


@pytest.fixture
def command_bus(registry: ToolRegistry) -> CommandBus:
    bus = CommandBus()
    event_bus = EventBus()
    security_guard = SecurityGuard(SecuritySettings(strict_mode=True, auto_approve_low_risk=True))
    handler = ExecuteToolCommandHandler(registry, security_guard, event_bus)
    bus.register(ExecuteToolCommand, handler)
    return bus


def test_prompt_builder_with_working_context() -> None:
    builder = PromptBuilder()
    context = WorkingContext(
        active_application="iTerm2",
        active_window_title="zsh - nexusai",
        git_branch="main",
        cpu_usage_percent=15.0,
        memory_usage_percent=50.0,
    )
    prompt = builder.build_system_prompt(context=context)

    assert "CURRENT WORKING CONTEXT:" in prompt
    assert "Active Application: iTerm2" in prompt
    assert "Git Branch: main" in prompt
    assert "CPU 15.0%" in prompt


@pytest.mark.asyncio
async def test_openai_provider_text_response() -> None:
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_message = MagicMock()
    mock_message.tool_calls = None
    mock_message.content = "Hello from OpenAI"
    mock_response.choices = [MagicMock(message=mock_message)]

    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

    provider = OpenAIProvider(client=mock_client)
    res = await provider.chat([{"role": "user", "content": "Hi"}])

    assert res == {"type": "text", "content": "Hello from OpenAI"}


@pytest.mark.asyncio
async def test_openai_provider_tool_call_response() -> None:
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_message = MagicMock()

    mock_tool_call = MagicMock()
    mock_tool_call.function.name = "open_app"
    mock_tool_call.function.arguments = '{"app_name": "Safari"}'

    mock_message.tool_calls = [mock_tool_call]
    mock_response.choices = [MagicMock(message=mock_message)]

    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

    provider = OpenAIProvider(client=mock_client)
    res = await provider.chat([{"role": "user", "content": "Open Safari"}])

    assert res == {
        "type": "tool_call",
        "tool_name": "open_app",
        "arguments": {"app_name": "Safari"},
    }


@pytest.mark.asyncio
async def test_brain_coordinator_text_flow(
    registry: ToolRegistry,
    command_bus: CommandBus,
) -> None:
    mock_provider = MockModelProvider({"type": "text", "content": "Hello User"})
    coordinator = BrainCoordinator(mock_provider, registry, command_bus)

    result = await coordinator.process_user_input("Hi NexusAI")

    assert result == {"type": "text", "content": "Hello User", "iterations": 1}
    assert len(mock_provider.last_messages) == 2
    assert mock_provider.last_tools is not None


@pytest.mark.asyncio
async def test_brain_coordinator_context_engine_integration(
    registry: ToolRegistry,
    command_bus: CommandBus,
) -> None:
    mock_provider = MockModelProvider({"type": "text", "content": "I see your active context"})
    mock_context_engine = AsyncMock()
    mock_context_engine.gather_context.return_value = WorkingContext(
        active_application="VS Code",
        active_window_title="coordinator.py",
        git_branch="feature/context",
        cpu_usage_percent=10.0,
        memory_usage_percent=40.0,
    )

    coordinator = BrainCoordinator(
        mock_provider,
        registry,
        command_bus,
        context_engine=mock_context_engine,
    )

    result = await coordinator.process_user_input("What is my current context?")
    assert result == {"type": "text", "content": "I see your active context", "iterations": 1}

    system_msg = mock_provider.last_messages[0]["content"]
    assert "Active Application: VS Code" in system_msg
    assert "Git Branch: feature/context" in system_msg


def test_openai_provider_missing_api_key_raises_error() -> None:
    with patch.dict("os.environ", {}, clear=True):
        with pytest.raises(ConfigurationError):
            OpenAIProvider()
