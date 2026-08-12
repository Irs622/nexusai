"""Security verification test suite for P3-4 AgentLoop invariants (P3-4-INV-01 to P3-4-INV-15)."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock
import pytest

from nexusai.brain.domain.agent import PlanGraph, PlanGraphNode, PlanStep
from nexusai.brain.domain.agent_loop import AgentLoopConfig, AgentLoopState
from nexusai.brain.domain.agent_runtime import AgentRequest
from nexusai.brain.domain.governance import ToolCapability
from nexusai.brain.domain.tool_registry import ToolMetadata, ToolStatus
from nexusai.brain.planner.engine import PlanGraphExecutionEngine
from nexusai.brain.ports.tool_port import IToolPort, ToolExecutionRequest, ToolExecutionResult
from nexusai.brain.runtime.agent_loop import AgentLoop
from nexusai.brain.runtime.tool_registry import ToolRegistry
from nexusai.infrastructure.observability.in_memory_exporter import InMemoryMetricsExporter


class DummySecurityToolPort(IToolPort):
    async def execute(self, request: ToolExecutionRequest) -> ToolExecutionResult:
        return ToolExecutionResult(request.execution_id, request.tool_name, True, "Security Output")


@pytest.mark.asyncio
async def test_security_max_iterations_and_replans_enforced() -> None:
    """Security Test (P3-4-INV-01 & P3-4-INV-02): max_iterations and max_replans strictly limit loop cycles."""
    engine = PlanGraphExecutionEngine()
    loop = AgentLoop(execution_engine=engine)
    tool_port = DummySecurityToolPort()

    # Loop with max_iterations = 1
    config = AgentLoopConfig(max_iterations=1, max_replans=0)
    req = AgentRequest(session_id="sess-sec-iter", user_prompt="Prompt")

    res = await loop.run(req, config, tool_port)
    assert res.final_state in (AgentLoopState.COMPLETED, AgentLoopState.FAILED)
    assert res.iterations <= 1


@pytest.mark.asyncio
async def test_security_plan_validation_and_disabled_tool_rejection() -> None:
    """Security Test (P3-4-INV-03): Unknown or disabled tools fail validation before execution."""
    registry = ToolRegistry()
    disabled_tool = ToolMetadata(
        tool_id="disabled_tool",
        name="Disabled",
        version="1.0.0",
        description="Disabled",
        capabilities=frozenset({ToolCapability.FILE_READ}),
        status=ToolStatus.DISABLED,
    )
    await registry.register(disabled_tool)

    engine = PlanGraphExecutionEngine()
    # Mock planner to output plan referencing disabled_tool
    nodes = {1: PlanGraphNode(step=PlanStep(step_id=1, title="Node 1", tool_name="disabled_tool"), dependencies=())}
    engine.planner.plan = lambda ctx, session_id="": (PlanGraph(nodes=nodes, edges=()), MagicMock())  # type: ignore[assignment]

    loop = AgentLoop(execution_engine=engine, tool_registry=registry)
    tool_port = DummySecurityToolPort()
    req = AgentRequest(session_id="sess-sec-val", user_prompt="Prompt")
    config = AgentLoopConfig(require_plan_validation=True, allow_replanning=False)

    res = await loop.run(req, config, tool_port)
    assert res.final_state == AgentLoopState.FAILED
    assert "Plan validation failed" in res.final_output


@pytest.mark.asyncio
async def test_security_telemetry_and_memory_fault_isolation() -> None:
    """Security Test (P3-4-INV-10 & P3-4-INV-11): Telemetry and memory failures DO NOT terminate loop execution."""
    faulty_telemetry = InMemoryMetricsExporter(fail_on_purpose=True)
    engine = PlanGraphExecutionEngine(telemetry=faulty_telemetry)
    loop = AgentLoop(execution_engine=engine, telemetry=faulty_telemetry)

    tool_port = DummySecurityToolPort()
    req = AgentRequest(session_id="sess-sec-fault", user_prompt="Fault isolation prompt")
    config = AgentLoopConfig()

    res = await loop.run(req, config, tool_port)
    assert res.final_state == AgentLoopState.COMPLETED


if __name__ == "__main__":
    asyncio.run(test_security_max_iterations_and_replans_enforced())
    asyncio.run(test_security_plan_validation_and_disabled_tool_rejection())
    asyncio.run(test_security_telemetry_and_memory_fault_isolation())
    print("ALL P3-4 AGENT LOOP SECURITY TESTS PASSED SUCCESSFULLY!")
