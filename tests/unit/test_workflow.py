"""
Unit tests for LangGraph Agentic Workflow nodes, state routing, and compiled graph.
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel, Field

from nexusai.brain.workflow.graph import build_agent_graph, should_continue
from nexusai.brain.workflow.nodes import node_reasoner, node_tool_executor
from nexusai.brain.workflow.state import NexusGraphState
from nexusai.bus.bus import CommandBus, EventBus
from nexusai.bus.commands import ExecuteToolCommand, ExecuteToolCommandHandler
from nexusai.core.config import SecuritySettings
from nexusai.models.base import BaseModelProvider
from nexusai.security.guard import RiskLevel, SecurityGuard
from nexusai.tools.base import BaseTool
from nexusai.tools.registry import ToolRegistry


class DummySchema(BaseModel):
    query: str = Field(..., description="Query")


class DummyTool(BaseTool):
    name = "dummy_tool"
    description = "Dummy tool"
    risk_level = RiskLevel.LOW
    input_schema = DummySchema

    async def execute(self, query: str, **kwargs: object) -> str:
        return f"Executed {query}"


class MockModelProvider(BaseModelProvider):
    def __init__(self, response: dict | list[dict]) -> None:
        self.responses = response if isinstance(response, list) else [response]
        self.call_count = 0

    async def chat(self, messages: list, tools: list | None = None) -> dict:
        resp = self.responses[min(self.call_count, len(self.responses) - 1)]
        self.call_count += 1
        return resp


@pytest.fixture
def registry() -> ToolRegistry:
    reg = ToolRegistry()
    reg.register(DummyTool())
    return reg


@pytest.fixture
def command_bus(registry: ToolRegistry) -> CommandBus:
    bus = CommandBus()
    event_bus = EventBus()
    security_guard = SecurityGuard(SecuritySettings(strict_mode=True, auto_approve_low_risk=True))
    handler = ExecuteToolCommandHandler(registry, security_guard, event_bus)
    bus.register(ExecuteToolCommand, handler)
    return bus


@pytest.mark.asyncio
async def test_node_reasoner_text_and_tool_call() -> None:
    text_provider = MockModelProvider({"type": "text", "content": "Answer"})
    state: NexusGraphState = {
        "session_id": "test",
        "messages": [{"role": "user", "content": "hi"}],
        "tools": None,
        "final_response": None,
        "iterations": 0,
        "user_confirmed": False,
        "max_iterations": 10,
        "last_tool_call": None,
    }

    res_text = await node_reasoner(state, text_provider)
    assert res_text["final_response"] == "Answer"
    assert res_text["iterations"] == 1

    tool_provider = MockModelProvider(
        {"type": "tool_call", "tool_name": "dummy_tool", "arguments": {"query": "abc"}}
    )
    res_tool = await node_reasoner(state, tool_provider)
    assert res_tool["last_tool_call"]["tool_name"] == "dummy_tool"
    assert res_tool["iterations"] == 1


@pytest.mark.asyncio
async def test_node_tool_executor(command_bus: CommandBus) -> None:
    state: NexusGraphState = {
        "session_id": "test",
        "messages": [{"role": "user", "content": "run tool"}],
        "tools": None,
        "final_response": None,
        "iterations": 1,
        "user_confirmed": False,
        "max_iterations": 10,
        "last_tool_call": {
            "type": "tool_call",
            "tool_name": "dummy_tool",
            "arguments": {"query": "hello"},
        },
    }

    res = await node_tool_executor(state, command_bus)
    assert res["last_tool_call"] is None
    new_msgs = res["messages"]
    assert len(new_msgs) == 2
    assert new_msgs[1]["role"] == "tool"
    assert new_msgs[1]["name"] == "dummy_tool"
    assert new_msgs[1]["content"] == "Executed hello"


def test_should_continue_router() -> None:
    state_done: NexusGraphState = {
        "session_id": "test",
        "messages": [],
        "tools": None,
        "final_response": "Done",
        "iterations": 1,
        "user_confirmed": False,
        "max_iterations": 10,
        "last_tool_call": None,
    }
    assert should_continue(state_done) == "__end__"

    state_max_iter: NexusGraphState = {
        "session_id": "test",
        "messages": [],
        "tools": None,
        "final_response": None,
        "iterations": 10,
        "user_confirmed": False,
        "max_iterations": 10,
        "last_tool_call": None,
    }
    assert should_continue(state_max_iter) == "__end__"

    state_continue: NexusGraphState = {
        "session_id": "test",
        "messages": [],
        "tools": None,
        "final_response": None,
        "iterations": 1,
        "user_confirmed": False,
        "max_iterations": 10,
        "last_tool_call": {"tool_name": "dummy_tool"},
    }
    assert should_continue(state_continue) == "tool_executor"


@pytest.mark.asyncio
async def test_compiled_agent_graph_execution(command_bus: CommandBus) -> None:
    responses = [
        {"type": "tool_call", "tool_name": "dummy_tool", "arguments": {"query": "world"}},
        {"type": "text", "content": "Graph completed successfully"},
    ]
    provider = MockModelProvider(responses)
    graph = build_agent_graph(provider, command_bus)

    initial_state: NexusGraphState = {
        "session_id": "graph_test",
        "messages": [{"role": "user", "content": "Start graph"}],
        "tools": None,
        "final_response": None,
        "iterations": 0,
        "user_confirmed": False,
        "max_iterations": 10,
        "last_tool_call": None,
    }

    final_state = await graph.ainvoke(initial_state)
    assert final_state["final_response"] == "Graph completed successfully"
    assert final_state["iterations"] == 2
