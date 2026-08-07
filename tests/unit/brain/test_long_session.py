"""Long Session Simulation Test — 50,000 Iteration Memory Safety Check."""

from __future__ import annotations

import asyncio
import gc
import tracemalloc
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
    """Dummy schema for benchmark tool."""


class FastMockTool(BaseTool):
    """Typed mock tool inheriting from BaseTool for type safety."""

    name = "fast_mock"
    description = "Fast mock tool"
    risk_level = RiskLevel.LOW
    input_schema = DummyInputSchema

    async def execute(self, *args: Any, **kwargs: Any) -> str:
        return "ok"


async def test_50k_iterations():
    logger.disable("nexusai")
    registry = ToolRegistry()
    registry.register(FastMockTool())
    tool_port = ToolRegistryAdapter(registry)

    facade = AgentRuntimeBuilder().with_tool_port(tool_port).build()
    session = BrainSession(session_id=uuid4(), conversation_id=uuid4())
    goal = AgentGoal(description="Long session goal")
    state = SessionState(provider_id="mock", active_model="mock-v1")

    gc.collect()
    tracemalloc.start()
    mem_samples: list[float] = []

    # Run 50,000 iterations in chunks of 5,000
    for chunk in range(10):
        for _ in range(5000):
            await facade.run_agent_session(session, goal, state)

        gc.collect()
        curr, peak = tracemalloc.get_traced_memory()
        mem_samples.append(round(curr / 1024.0, 2))

    tracemalloc.stop()

    print(f"Memory samples across 50,000 iterations (KB): {mem_samples}")
    delta_kb = mem_samples[-1] - mem_samples[0]
    print(f"Total memory delta across 50,000 iterations: {delta_kb:.2f} KB")
    assert delta_kb < 500.0, f"Memory leak detected: grew by {delta_kb:.2f} KB!"
    print("50,000 ITERATION LONG SESSION SIMULATION COMPLETED SUCCESSFULLY!")


if __name__ == "__main__":
    asyncio.run(test_50k_iterations())
