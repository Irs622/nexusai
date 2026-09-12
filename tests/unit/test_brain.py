"""
Unit tests for Model Providers, Prompt Builder, Brain Coordinator, and Context Engine Integration.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel, Field

from nexusai.brain.coordinator import BrainCoordinator
from nexusai.brain.prompt import PromptBuilder
from nexusai.bus.bus import CommandBus, EventBus
from nexusai.bus.commands import ExecuteToolCommand, ExecuteToolCommandHandler
from nexusai.context.engine import WorkingContext
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
    def __init__(self, response: dict[str, Any] | list[dict[str, Any]]) -> None:
        self.responses = response if isinstance(response, list) else [response]
        self.call_count = 0
        self.last_messages: list[dict[str, Any]] = []
        self.last_tools: list[dict[str, Any]] | None = None

    async def chat(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None
    ) -> dict[str, Any]:
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
def command_bus(registry: ToolRegistry, security_guard: SecurityGuard) -> CommandBus:
    bus = CommandBus()
    event_bus = EventBus()
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

    assert result["type"] == "text"
    assert result["content"] == "Hello User"
    assert result["iterations"] == 1
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
    assert result["type"] == "text"
    assert result["content"] == "I see your active context"
    assert result["iterations"] == 1

    system_msg = mock_provider.last_messages[0]["content"]
    assert "Active Application: VS Code" in system_msg
    assert "Git Branch: feature/context" in system_msg


def test_openai_provider_missing_api_key_raises_error() -> None:
    with patch.dict("os.environ", {}, clear=True):
        with pytest.raises(ConfigurationError):
            OpenAIProvider()


@pytest.mark.asyncio
async def test_brain_coordinator_tool_call_flow(
    registry: ToolRegistry,
    command_bus: CommandBus,
) -> None:
    """Verify coordinator receives tool_call, dispatches tool, and returns synthesized text."""
    from pydantic import BaseModel

    from nexusai.tools.base import BaseTool

    class DummyInput(BaseModel):
        msg: str = "default"

    class DummyTool(BaseTool):
        name: str = "dummy_notify"
        description: str = "Test notify tool"
        input_schema: type[BaseModel] = DummyInput

        async def execute(self, **kwargs: Any) -> str:
            return "Notification sent successfully!"

    registry.register(DummyTool())

    # Provider returns tool_call first, then text response
    calls: list[dict[str, Any]] = [
        {"type": "tool_call", "tool_name": "dummy_notify", "arguments": {"msg": "Hello"}},
        {"type": "text", "content": "I have sent the notification for you!"},
    ]

    class SequentialMockProvider:
        def __init__(self) -> None:
            self.call_count = 0
            self.last_messages: list[dict[str, Any]] = []
            self.last_tools: list[dict[str, Any]] | None = None

        async def chat(self, messages: list[dict[str, Any]], tools: Any = None) -> dict[str, Any]:
            self.last_messages = messages
            ret = calls[min(self.call_count, len(calls) - 1)]
            self.call_count += 1
            return ret

    provider = SequentialMockProvider()
    coordinator = BrainCoordinator(provider, registry, command_bus)

    result = await coordinator.process_user_input("Send notification")
    assert result["type"] == "text"
    assert result["content"] == "I have sent the notification for you!"
    assert provider.call_count == 2
    # Verify tool message was included in second prompt to LLM
    assert any(m.get("role") == "tool" for m in provider.last_messages)


@pytest.mark.asyncio
async def test_coordinator_critical_tool_blocked_without_approval(
    registry: ToolRegistry,
    command_bus: CommandBus,
    security_guard: SecurityGuard,
) -> None:
    from pydantic import BaseModel

    from nexusai.security.guard import RiskLevel
    from nexusai.tools.base import BaseTool

    class CriticalInput(BaseModel):
        target: str = "database"

    class CriticalTool(BaseTool):
        name: str = "critical_truncate"
        description: str = "Destructive action"
        risk_level: RiskLevel = RiskLevel.CRITICAL
        input_schema: type[BaseModel] = CriticalInput

        async def execute(self, **kwargs: Any) -> str:
            return "DATABASE_TRUNCATED"

    registry.register(CriticalTool())

    calls: list[dict[str, Any]] = [
        {"type": "tool_call", "tool_name": "critical_truncate", "arguments": {"target": "prod"}},
        {"type": "text", "content": "Attempted to execute tool."},
    ]

    class MockProvider:
        def __init__(self) -> None:
            self.call_count = 0
            self.last_messages: list[dict[str, Any]] = []

        async def chat(self, messages: list[dict[str, Any]], tools: Any = None) -> dict[str, Any]:
            self.last_messages = messages
            ret = calls[min(self.call_count, len(calls) - 1)]
            self.call_count += 1
            return ret

    # 1. Without approval token, execution is blocked
    provider1 = MockProvider()
    coordinator1 = BrainCoordinator(provider1, registry, command_bus)
    await coordinator1.process_user_input("Truncate prod DB")
    # Verify tool call failed with security denial in tool message
    tool_msg = next((m for m in provider1.last_messages if m.get("role") == "tool"), None)
    assert tool_msg is not None
    assert "Security policy denied" in tool_msg.get("content", "")

    # 2. With valid approval token, tool executes
    token, _ = security_guard.approval_service.create_token(
        tool_name="critical_truncate",
        arguments={"target": "prod"},
        execution_id="sess_approved",
    )
    provider2 = MockProvider()
    coordinator2 = BrainCoordinator(provider2, registry, command_bus)
    await coordinator2.process_user_input(
        "Truncate prod DB",
        session_id="sess_approved",
        approval_token=token,
    )
    tool_msg2 = next((m for m in provider2.last_messages if m.get("role") == "tool"), None)
    assert tool_msg2 is not None
    assert "DATABASE_TRUNCATED" in str(tool_msg2.get("content"))

    # 3. With HumanApprovalEngine grant bound to exact action, tool executes
    from nexusai.brain.domain.governance import ToolCapability
    from nexusai.brain.domain.human_approval import (
        ActionBinding,
        ApprovalStatus,
        HumanApprovalDecision,
        HumanApprovalRequest,
        RiskLevel,
    )
    from nexusai.brain.runtime.human_approval_engine import HumanApprovalEngine

    approval_engine = HumanApprovalEngine()
    security_guard.human_approval_engine = approval_engine

    binding = ActionBinding(
        session_id="sess_approved_grant",
        execution_id="exec-123",
        plan_fingerprint="fp-123",
        node_id="node-123",
        tool_id="critical_truncate",
        tool_version="1.0.0",
        requested_capabilities=frozenset({ToolCapability.PROCESS_EXEC}),
        resource_scope="/",
    )
    req_appr = HumanApprovalRequest(
        approval_id="appr-test-123",
        binding=binding,
        risk_level=RiskLevel.CRITICAL,
        prompt_summary="Truncate prod DB",
    )
    await approval_engine.request_approval(req_appr)
    decision = HumanApprovalDecision(
        approval_id="appr-test-123",
        status=ApprovalStatus.APPROVED,
        actor="lead-admin",
        reason="Authorized test execution",
    )
    grant = await approval_engine.submit_decision(decision)

    provider3 = MockProvider()
    coordinator3 = BrainCoordinator(provider3, registry, command_bus)
    await coordinator3.process_user_input(
        "Truncate prod DB",
        session_id="sess_approved_grant",
        approval_token=grant.grant_id,
    )
    tool_msg3 = next((m for m in provider3.last_messages if m.get("role") == "tool"), None)
    assert tool_msg3 is not None
    assert "DATABASE_TRUNCATED" in str(tool_msg3.get("content"))
