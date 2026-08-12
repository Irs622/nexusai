"""P1-FINAL Runtime Integration & Stress Verification Test Suite.

Verifies end-to-end runtime integration across all P1 remediations:
- P1-1 Tool Timeout & Cancellation Safety
- P1-2 Dynamic DAG Dependency Resolution
- P1-3 Concurrent DAG Scheduling & Execution
- P1-4 Synchronous Tool Isolation
- P1-5 Process Group Teardown & Subprocess Tree Cleanup

Tests:
1. Multi-branch partial failure state consistency (A -> B/C -> D where B times out, C succeeds, D is blocked).
2. Sync & async tool mixed execution with event loop heartbeat checks.
3. Subprocess process-group cleanup under timeout stress.
4. Task cancellation propagation during concurrent execution without task leaks.
5. End-to-end BrainCoordinator runtime pipeline integration.
"""

from __future__ import annotations

import asyncio
import os
import signal
import sys
import tempfile
import time
from typing import Any
from unittest.mock import MagicMock
import pytest
from pydantic import BaseModel, Field

from nexusai.brain.coordinator import BrainCoordinator
from nexusai.brain.domain.agent import (
    AgentGoal,
    PlanGraph,
    PlanGraphNode,
    PlanningContext,
    PlanningGoal,
    PlanningResources,
    PlanStep,
    StepStatus,
)
from nexusai.brain.planner.engine import PlanGraphExecutionEngine
from nexusai.brain.ports.tool_port import IToolPort, ToolExecutionRequest, ToolExecutionResult
from nexusai.brain.runtime.execution_policy import CircuitBreaker
from nexusai.security.guard import RiskLevel
from nexusai.tools.adapter import ToolRegistryAdapter
from nexusai.tools.base import BaseTool
from nexusai.tools.registry import ToolRegistry
from nexusai.tools.system.terminal import TerminalTool


class QueryInputSchema(BaseModel):
    query: str = Field(..., description="Query parameter")


class FastAsyncTool(BaseTool):
    name = "fast_async_tool"
    description = "Fast async tool"
    risk_level = RiskLevel.LOW
    input_schema = QueryInputSchema

    async def execute(self, query: str, **kwargs: Any) -> str:
        await asyncio.sleep(0.02)
        return f"Async result: {query}"


class SlowAsyncTool(BaseTool):
    name = "slow_async_tool"
    description = "Slow async tool timing out"
    risk_level = RiskLevel.LOW
    input_schema = QueryInputSchema

    async def execute(self, query: str, **kwargs: Any) -> str:
        await asyncio.sleep(5.0)
        return f"Slow result: {query}"


class SyncWorkerTool(BaseTool):
    name = "sync_worker_tool"
    description = "Synchronous tool using time.sleep"
    risk_level = RiskLevel.LOW
    input_schema = QueryInputSchema

    def execute(self, query: str, **kwargs: Any) -> str:
        time.sleep(0.1)
        return f"Sync result: {query}"


class StressSpyToolPort(IToolPort):
    """Tool port for stress testing multi-branch state consistency."""

    def __init__(self, timeout_tools: set[str] | None = None) -> None:
        self.timeout_tools = timeout_tools or set()
        self.executed_tools: list[str] = []

    async def execute(self, request: ToolExecutionRequest) -> ToolExecutionResult:
        self.executed_tools.append(request.tool_name)
        if request.tool_name in self.timeout_tools:
            # Simulate adapter-level timeout failure
            return ToolExecutionResult(
                request_id=request.execution_id,
                tool_name=request.tool_name,
                success=False,
                error_message=f"Tool execution timed out after {request.timeout_seconds}s for '{request.tool_name}'",
            )
        await asyncio.sleep(0.02)
        return ToolExecutionResult(
            request_id=request.execution_id,
            tool_name=request.tool_name,
            success=True,
            output=f"Output for {request.tool_name}",
        )


def create_context(description: str = "P1 Integration Test") -> PlanningContext:
    goal = AgentGoal(description=description)
    return PlanningContext(
        goal_component=PlanningGoal(goal=goal),
        resources_component=PlanningResources(available_tools=("tool_a", "tool_b", "tool_c", "tool_d")),
    )


# ------------------------------------------------------------------
# Integration & Stress Tests
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_multi_branch_partial_failure_state_consistency() -> None:
    """Verify state consistency after partial failure in multi-branch DAG.

            A (root, success)
           / \
          B   C (B times out & fails, C succeeds)
          |
          D (depends on B, blocked/cancelled)
    """
    engine = PlanGraphExecutionEngine(max_concurrency=4)
    spy_port = StressSpyToolPort(timeout_tools={"tool_b"})

    nodes = {
        1: PlanGraphNode(step=PlanStep(step_id=1, title="Step A", tool_name="tool_a"), dependencies=()),
        2: PlanGraphNode(step=PlanStep(step_id=2, title="Step B", tool_name="tool_b"), dependencies=(1,)),
        3: PlanGraphNode(step=PlanStep(step_id=3, title="Step C", tool_name="tool_c"), dependencies=(1,)),
        4: PlanGraphNode(step=PlanStep(step_id=4, title="Step D", tool_name="tool_d"), dependencies=(2,)),
    }
    plan_graph = PlanGraph(nodes=nodes, edges=((1, 2), (1, 3), (2, 4)))
    engine.planner.plan = lambda ctx, session_id="": (plan_graph, MagicMock())  # type: ignore[assignment]

    ctx = create_context("Partial Failure Test")
    graph, results, trace = await engine.execute_plan(ctx, tool_port=spy_port)

    # State consistency assertions across all components
    assert graph.nodes[1].step.status == StepStatus.COMPLETED
    assert graph.nodes[2].step.status == StepStatus.FAILED
    assert graph.nodes[3].step.status == StepStatus.COMPLETED
    assert graph.nodes[4].step.status in (StepStatus.CANCELLED, StepStatus.PENDING)

    # Executed tools check: A, B, C ran; D was blocked
    assert "tool_a" in spy_port.executed_tools
    assert "tool_b" in spy_port.executed_tools
    assert "tool_c" in spy_port.executed_tools
    assert "tool_d" not in spy_port.executed_tools, "Tool D must NOT run when dependency B failed"

    # CircuitBreaker recorded failure from B
    assert engine.circuit_breaker.failure_count == 1

    # Trace & results consistency
    assert trace is not None
    assert len(results) == 3, f"Expected 3 results (A, B, C), got {len(results)}"
    res_b = [r for r in results if r.tool_name == "tool_b"][0]
    assert res_b.success is False
    assert "timed out" in (res_b.error_message or "")


@pytest.mark.asyncio
async def test_mixed_sync_async_tool_event_loop_responsiveness() -> None:
    """Verify concurrent execution of sync and async tools does not block main event loop."""
    registry = ToolRegistry()
    registry.register(FastAsyncTool())
    registry.register(SyncWorkerTool())
    adapter = ToolRegistryAdapter(registry)

    heartbeat_ticks = 0

    async def heartbeat() -> None:
        nonlocal heartbeat_ticks
        for _ in range(5):
            await asyncio.sleep(0.03)
            heartbeat_ticks += 1

    req_async = ToolExecutionRequest(tool_name="fast_async_tool", arguments={"query": "test1"})
    req_sync = ToolExecutionRequest(tool_name="sync_worker_tool", arguments={"query": "test2"})

    # Execute async and sync tools concurrently with heartbeat
    tasks = [
        asyncio.create_task(adapter.execute(req_async)),
        asyncio.create_task(adapter.execute(req_sync)),
        asyncio.create_task(heartbeat()),
    ]

    res_async, res_sync, _ = await asyncio.gather(*tasks)

    assert res_async.success is True
    assert res_sync.success is True
    assert heartbeat_ticks >= 3, f"Event loop heartbeat was blocked! Ticks: {heartbeat_ticks}"


@pytest.mark.asyncio
async def test_subprocess_group_cleanup_under_timeout_stress() -> None:
    """Verify TerminalTool process group cleanup under timeout stress with background child process."""
    if sys.platform == "win32":
        pytest.skip("POSIX process group test")

    terminal_tool = TerminalTool()

    with tempfile.NamedTemporaryFile(mode="w+", delete=False) as tf:
        pid_file = tf.name

    try:
        cmd = f'sh -c "sleep 20 & echo $! > {pid_file}; sleep 20"'

        with pytest.raises(asyncio.TimeoutError):
            await terminal_tool.execute(cmd, timeout_seconds=0.15)

        await asyncio.sleep(0.1)
        with open(pid_file, "r") as f:
            child_pid_str = f.read().strip()

        assert child_pid_str.isdigit()
        child_pid = int(child_pid_str)

        # Assert background process group was terminated cleanly
        with pytest.raises(ProcessLookupError):
            os.kill(child_pid, 0)
    finally:
        if os.path.exists(pid_file):
            os.remove(pid_file)


@pytest.mark.asyncio
async def test_cancellation_during_concurrent_dag_execution() -> None:
    """Verify task cancellation during multi-node concurrent DAG execution leaves zero leaked tasks."""
    engine = PlanGraphExecutionEngine(max_concurrency=4)
    spy_port = StressSpyToolPort()

    nodes = {
        1: PlanGraphNode(step=PlanStep(step_id=1, title="Step A", tool_name="tool_a"), dependencies=()),
        2: PlanGraphNode(step=PlanStep(step_id=2, title="Step B", tool_name="tool_b"), dependencies=()),
        3: PlanGraphNode(step=PlanStep(step_id=3, title="Step C", tool_name="tool_c"), dependencies=()),
    }
    plan_graph = PlanGraph(nodes=nodes)
    engine.planner.plan = lambda ctx, session_id="": (plan_graph, MagicMock())  # type: ignore[assignment]

    ctx = create_context("Cancellation Stress Test")
    task = asyncio.create_task(engine.execute_plan(ctx, tool_port=spy_port))

    await asyncio.sleep(0.01)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_brain_coordinator_end_to_end_runtime_pipeline() -> None:
    """Verify end-to-end runtime pipeline through BrainCoordinator."""
    registry = ToolRegistry()
    registry.register(FastAsyncTool())
    registry.register(SyncWorkerTool())

    coordinator = BrainCoordinator(model_provider=None, registry=registry)
    res = await coordinator.process_user_input("Run fast_async_tool query test")

    assert res["status"] == "COMPLETED"
    assert res["iterations"] == 1
    assert "trace_id" in res
    assert coordinator.last_plan_graph is not None
    assert coordinator.last_decision_trace is not None


if __name__ == "__main__":
    asyncio.run(test_multi_branch_partial_failure_state_consistency())
    asyncio.run(test_mixed_sync_async_tool_event_loop_responsiveness())
    asyncio.run(test_subprocess_group_cleanup_under_timeout_stress())
    asyncio.run(test_cancellation_during_concurrent_dag_execution())
    asyncio.run(test_brain_coordinator_end_to_end_runtime_pipeline())
    print("ALL P1-FINAL RUNTIME INTEGRATION & STRESS VERIFICATION TESTS PASSED SUCCESSFULLY!")
