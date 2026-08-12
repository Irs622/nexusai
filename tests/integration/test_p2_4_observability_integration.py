"""Integration and overhead verification test suite for P2-4 Observability, Telemetry, and Correlation Lifecycle."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import MagicMock
import pytest

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
from nexusai.brain.domain.observability import RuntimeEventType
from nexusai.brain.domain.recovery import ToolExecutionPolicy
from nexusai.brain.planner.engine import PlanGraphExecutionEngine
from nexusai.brain.ports.tool_port import IToolPort, ToolExecutionRequest, ToolExecutionResult
from nexusai.brain.runtime.priority_scheduler import PriorityScheduler
from nexusai.infrastructure.observability.in_memory_exporter import InMemoryMetricsExporter


class DummyObsToolPort(IToolPort):
    """ToolPort executing simple steps for observability verification."""

    async def execute(self, request: ToolExecutionRequest) -> ToolExecutionResult:
        await asyncio.sleep(0.005)
        return ToolExecutionResult(
            request_id=request.execution_id,
            tool_name=request.tool_name,
            success=True,
            output=f"Output for {request.tool_name}",
        )


def create_obs_context() -> PlanningContext:
    goal = AgentGoal(description="P2-4 Observability Integration Context")
    tools = ("tool_1", "tool_2", "tool_3")
    return PlanningContext(
        goal_component=PlanningGoal(goal=goal),
        resources_component=PlanningResources(available_tools=tools),
    )


def create_obs_graph() -> PlanGraph:
    nodes = {
        1: PlanGraphNode(step=PlanStep(step_id=1, title="Step 1", tool_name="tool_1"), dependencies=()),
        2: PlanGraphNode(step=PlanStep(step_id=2, title="Step 2", tool_name="tool_2"), dependencies=(1,)),
        3: PlanGraphNode(step=PlanStep(step_id=3, title="Step 3", tool_name="tool_3"), dependencies=(2,)),
    }
    return PlanGraph(nodes=nodes, edges=((1, 2), (2, 3)))


@pytest.mark.asyncio
async def test_full_execution_lifecycle_telemetry_correlation() -> None:
    """Test A & I: Full execution lifecycle emits correlated events and metrics across pipeline."""
    exporter = InMemoryMetricsExporter()
    scheduler = PriorityScheduler(aging_rate=0.5, telemetry=exporter)
    engine = PlanGraphExecutionEngine(scheduler=scheduler, telemetry=exporter)

    graph = create_obs_graph()
    engine.planner.plan = lambda ctx, session_id="": (graph, MagicMock())  # type: ignore[assignment]

    tool_port = DummyObsToolPort()
    ctx = create_obs_context()

    rec_graph, results, trace = await engine.execute_plan(
        ctx, tool_port, session_id="plan-obs", execution_id="exec-obs-100"
    )

    snap = exporter.snapshot()

    # Verify correlated events presence
    event_types = [e.event_type for e in snap.events]
    assert RuntimeEventType.EXECUTION_STARTED in event_types
    assert RuntimeEventType.NODE_STARTED in event_types
    assert RuntimeEventType.TOOL_STARTED in event_types
    assert RuntimeEventType.TOOL_COMPLETED in event_types
    assert RuntimeEventType.NODE_COMPLETED in event_types
    assert RuntimeEventType.EXECUTION_COMPLETED in event_types

    # Verify event correlation with execution_id
    for evt in snap.events:
        if evt.execution_id:
            assert evt.execution_id == "exec-obs-100"

    # Verify metrics counters and durations recorded
    assert snap.counters.get("nexusai_executions_total") == 1
    assert snap.counters.get("nexusai_executions_completed_total") == 1
    assert snap.counters.get("nexusai_nodes_completed_total") == 3
    assert snap.counters.get("nexusai_tool_executions_total") == 3
    assert len(snap.duration_samples.get("nexusai_execution_duration_ms", [])) == 1


@pytest.mark.asyncio
async def test_exporter_fault_isolation_under_engine_execution() -> None:
    """Test K: Engine execution completes 100% successfully even when telemetry exporter throws runtime exceptions."""
    faulty_exporter = InMemoryMetricsExporter(fail_on_purpose=True)
    scheduler = PriorityScheduler(aging_rate=0.5, telemetry=faulty_exporter)
    engine = PlanGraphExecutionEngine(scheduler=scheduler, telemetry=faulty_exporter)

    graph = create_obs_graph()
    engine.planner.plan = lambda ctx, session_id="": (graph, MagicMock())  # type: ignore[assignment]

    tool_port = DummyObsToolPort()
    ctx = create_obs_context()

    # Execute plan - must complete successfully without crashing
    rec_graph, results, trace = await engine.execute_plan(ctx, tool_port, execution_id="exec-faulty-obs")

    assert rec_graph.nodes[1].step.status == StepStatus.COMPLETED
    assert rec_graph.nodes[2].step.status == StepStatus.COMPLETED
    assert rec_graph.nodes[3].step.status == StepStatus.COMPLETED
    assert len(results) == 3


@pytest.mark.asyncio
async def test_runtime_overhead_baseline_benchmark() -> None:
    """Test Requirement 16: Measure and establish empirical runtime overhead baseline with telemetry enabled vs disabled."""
    ctx = create_obs_context()
    tool_port = DummyObsToolPort()

    # Benchmark Without Telemetry
    engine_no_obs = PlanGraphExecutionEngine(telemetry=None)
    engine_no_obs.planner.plan = lambda ctx, session_id="": (create_obs_graph(), MagicMock())  # type: ignore[assignment]

    t0 = time.perf_counter()
    for i in range(10):
        await engine_no_obs.execute_plan(ctx, tool_port, execution_id=f"exec-noobs-{i}")
    dur_no_obs_ms = (time.perf_counter() - t0) * 1000.0

    # Benchmark With Telemetry
    exporter = InMemoryMetricsExporter()
    engine_with_obs = PlanGraphExecutionEngine(telemetry=exporter)
    engine_with_obs.planner.plan = lambda ctx, session_id="": (create_obs_graph(), MagicMock())  # type: ignore[assignment]

    t0 = time.perf_counter()
    for i in range(10):
        await engine_with_obs.execute_plan(ctx, tool_port, execution_id=f"exec-withobs-{i}")
    dur_with_obs_ms = (time.perf_counter() - t0) * 1000.0

    diff_ms = dur_with_obs_ms - dur_no_obs_ms
    per_exec_overhead_ms = diff_ms / 10.0

    print(f"\n[OBSERVED TELEMETRY OVERHEAD BASELINE]")
    print(f"10 Executions Without Telemetry : {dur_no_obs_ms:.2f} ms")
    print(f"10 Executions With Telemetry    : {dur_with_obs_ms:.2f} ms")
    print(f"Per-Execution Telemetry Overhead: {per_exec_overhead_ms:.3f} ms")

    assert per_exec_overhead_ms < 5.0, "Telemetry overhead per execution must be under 5ms"


if __name__ == "__main__":
    asyncio.run(test_full_execution_lifecycle_telemetry_correlation())
    asyncio.run(test_exporter_fault_isolation_under_engine_execution())
    asyncio.run(test_runtime_overhead_baseline_benchmark())
    print("ALL P2-4 OBSERVABILITY INTEGRATION TESTS PASSED SUCCESSFULLY!")
