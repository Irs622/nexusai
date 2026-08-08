"""Concurrent Session Stress Test — 100 Simultaneous Active Sessions."""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import uuid4

from loguru import logger
from pydantic import BaseModel

from nexusai.brain.builder import AgentRuntimeBuilder
from nexusai.brain.domain.agent import AgentGoal
from nexusai.brain.domain.session import BrainSession
from nexusai.brain.runtime.state import SessionState
from nexusai.security.guard import RiskLevel
from nexusai.tools.adapter import ToolRegistryAdapter
from nexusai.tools.base import BaseTool
from nexusai.tools.registry import ToolRegistry


class DummyInputSchema(BaseModel):
    """Dummy schema for concurrent test tool."""


class ConcurrentMockTool(BaseTool):
    """Typed mock tool inheriting from BaseTool for type safety."""

    name = "concurrent_tool"
    description = "Concurrent test tool"
    risk_level = RiskLevel.LOW
    input_schema = DummyInputSchema

    async def execute(self, *args: Any, **kwargs: Any) -> str:
        return "concurrent_ok"


async def test_concurrent_100_sessions():
    logger.disable("nexusai")
    registry = ToolRegistry()
    registry.register(ConcurrentMockTool())
    tool_port = ToolRegistryAdapter(registry)

    facade = AgentRuntimeBuilder().with_tool_port(tool_port).build()

    async def run_single_session(session_idx: int):
        session = BrainSession(session_id=uuid4(), conversation_id=uuid4())
        goal = AgentGoal(description=f"Concurrent Goal {session_idx}")
        state = SessionState(provider_id="mock", active_model="mock-v1")
        response = await facade.run_agent_session(session, goal, state)
        assert response is not None
        assert response.working_memory.goal.description == f"Concurrent Goal {session_idx}"
        return response

    print("Launching 100 concurrent agent sessions via asyncio.gather()...")
    tasks = [run_single_session(i) for i in range(100)]
    responses = await asyncio.gather(*tasks)

    assert len(responses) == 100
    # Verify every session retained its distinct goal and memory without cross-talk
    descriptions = {r.working_memory.goal.description for r in responses}
    assert len(descriptions) == 100, "State corruption detected across concurrent sessions!"

    print("100 CONCURRENT SESSIONS STRESS TEST PASSED SUCCESSFULLY!")


if __name__ == "__main__":
    asyncio.run(test_concurrent_100_sessions())
