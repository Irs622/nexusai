"""Integration test suite for P2-5 GovernanceEngine, PlanGraphExecutionEngine, and BrainCoordinator integration."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock
import pytest

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
from nexusai.brain.domain.governance import ResourceBudget, ToolCapability
from nexusai.brain.planner.engine import PlanGraphExecutionEngine
from nexusai.brain.ports.tool_port import IToolPort, ToolExecutionRequest, ToolExecutionResult
from nexusai.brain.runtime.governance_engine import GovernanceEngine


class GovDummyToolPort(IToolPort):
    """ToolPort executing steps for governance integration testing."""

    async def execute(self, request: ToolExecutionRequest) -> ToolExecutionResult:
        await asyncio.sleep(0.005)
        return ToolExecutionResult(
            request_id=request.execution_id,
            tool_name=request.tool_name,
            success=True,
            output=f"Output for {request.tool_name}",
        )


def create_gov_context() -> PlanningContext:
    goal = AgentGoal(description="P2-5 Governance Integration Context")
    tools = ("terminal", "file_reader", "unregistered_tool")
    return PlanningContext(
        goal_component=PlanningGoal(goal=goal),
        resources_component=PlanningResources(available_tools=tools),
    )


@pytest.mark.asyncio
async def test_p2_5_dag_with_authorized_and_unauthorized_tools() -> None:
    """Integration Test 1: DAG with authorized terminal tool and unauthorized unregistered_tool."""
    gov = GovernanceEngine()
    engine = PlanGraphExecutionEngine(governance=gov)

    nodes = {
        1: PlanGraphNode(step=PlanStep(step_id=1, title="Authorized", tool_name="terminal"), dependencies=()),
        2: PlanGraphNode(step=PlanStep(step_id=2, title="Unauthorized", tool_name="unregistered_tool"), dependencies=(1,)),
    }
    plan_graph = PlanGraph(nodes=nodes, edges=((1, 2),))
    engine.planner.plan = lambda ctx, session_id="": (plan_graph, MagicMock())  # type: ignore[assignment]

    tool_port = GovDummyToolPort()
    ctx = create_gov_context()

    rec_graph, results, trace = await engine.execute_plan(ctx, tool_port, execution_id="exec-gov-1")

    assert rec_graph.nodes[1].step.status == StepStatus.COMPLETED
    assert rec_graph.nodes[2].step.status == StepStatus.FAILED
    assert "Governance denied" in results[1].error_message
    # Confirm reservation was released cleanly
    assert gov.get_active_reservation_count() == 0


@pytest.mark.asyncio
async def test_p2_5_end_to_end_brain_coordinator_governance() -> None:
    """Integration Test 8: BrainCoordinator end-to-end execution with GovernanceEngine."""
    gov = GovernanceEngine()
    engine = PlanGraphExecutionEngine(governance=gov)
    coordinator = BrainCoordinator(model_provider=None, execution_engine=engine)

    res = await coordinator.process_user_input("P2-5 Governed query")

    assert res["status"] == "COMPLETED"
    assert res["iterations"] == 1
    assert gov.get_active_reservation_count() == 0


if __name__ == "__main__":
    asyncio.run(test_p2_5_dag_with_authorized_and_unauthorized_tools())
    asyncio.run(test_p2_5_end_to_end_brain_coordinator_governance())
    print("ALL P2-5 GOVERNANCE INTEGRATION TESTS PASSED SUCCESSFULLY!")
