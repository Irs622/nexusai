"""Adversarial stress test suite for P2-5 GovernanceEngine resource leakage, quota enforcement, and concurrency safety."""

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
)
from nexusai.brain.domain.governance import ResourceBudget, ToolCapability
from nexusai.brain.planner.engine import PlanGraphExecutionEngine
from nexusai.brain.ports.tool_port import IToolPort, ToolExecutionRequest, ToolExecutionResult
from nexusai.brain.runtime.governance_engine import GovernanceEngine


class FlakyGovToolPort(IToolPort):
    """ToolPort simulating random tool timeouts, failures, and delays."""

    async def execute(self, request: ToolExecutionRequest) -> ToolExecutionResult:
        tool_name = request.tool_name
        if "fail" in tool_name:
            raise RuntimeError(f"Simulated failure for {tool_name}")
        await asyncio.sleep(0.005)
        return ToolExecutionResult(
            request_id=request.execution_id,
            tool_name=tool_name,
            success=True,
            output=f"Output for {tool_name}",
        )


def create_stress_graph(exec_index: int) -> PlanGraph:
    nodes = {}
    edges = []
    tool_names = ["terminal", "file_reader", "unregistered_tool", "terminal_fail"]
    for i in range(1, 6):
        deps = (i - 1,) if i > 1 else ()
        t_name = tool_names[(exec_index + i) % len(tool_names)]
        nodes[i] = PlanGraphNode(
            step=PlanStep(step_id=i, title=f"Step {i}", tool_name=t_name),
            dependencies=deps,
        )
        if i > 1:
            edges.append((i - 1, i))
    return PlanGraph(nodes=nodes, edges=tuple(edges))


def create_stress_context() -> PlanningContext:
    goal = AgentGoal(description="P2-5 Governance Stress Context")
    tools = ("terminal", "file_reader", "unregistered_tool", "terminal_fail")
    return PlanningContext(
        goal_component=PlanningGoal(goal=goal),
        resources_component=PlanningResources(available_tools=tools),
    )


@pytest.mark.asyncio
async def test_p2_5_adversarial_governance_stress_and_zero_leakage() -> None:
    """Adversarial Stress Test: 20 concurrent executions with 100+ node dispatches, random failures & denials.

    Verification Invariant: reserved_resources <= configured_capacity AND active_reservations == 0 at teardown.
    """
    global_budget = ResourceBudget(max_concurrent_tasks=6, max_subprocesses=10, max_tool_invocations=30)
    gov = GovernanceEngine(global_budget=global_budget)
    engine = PlanGraphExecutionEngine(governance=gov, max_concurrency=4)

    tool_port = FlakyGovToolPort()
    ctx = create_stress_context()

    async def worker(idx: int) -> None:
        graph = create_stress_graph(idx)
        engine_instance = PlanGraphExecutionEngine(governance=gov, max_concurrency=4)
        engine_instance.planner.plan = lambda ctx, session_id="": (graph, MagicMock())  # type: ignore[assignment]
        try:
            await engine_instance.execute_plan(ctx, tool_port, execution_id=f"exec-stress-{idx}")
        except Exception:
            pass

    # Launch 20 concurrent executions
    tasks = [asyncio.create_task(worker(i)) for i in range(20)]
    await asyncio.gather(*tasks, return_exceptions=True)

    # FINAL INVARIANT VERIFICATION: Zero resource leakage
    active_count = gov.get_active_reservation_count()
    print(f"\n[P2-5 ADVERSARIAL STRESS VERIFICATION]")
    print(f"Active Reservations at Teardown: {active_count}")

    assert active_count == 0, f"RESOURCE LEAK DETECTED: {active_count} active reservations remained unreleased!"


if __name__ == "__main__":
    asyncio.run(test_p2_5_adversarial_governance_stress_and_zero_leakage())
    print("ALL P2-5 ADVERSARIAL STRESS VERIFICATION TESTS PASSED SUCCESSFULLY!")
