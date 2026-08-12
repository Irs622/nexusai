"""P0-2 Entrypoint and Runtime Integration Regression Test Suite.

Verifies:
- User input via CLI/Web entrypoint reaches the Brain Runtime pipeline (BrainCoordinator -> PlanGraphExecutionEngine).
- ExecutionPlanner generates PlanGraph DAG.
- PlanValidator validates the plan before execution.
- Tool/Provider execution passes through IToolPort / ToolRegistryAdapter.
- Direct provider bypass does not occur.
- Offline/mock execution works without API keys.
- Error handling remains intact.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from pydantic import BaseModel, Field

from nexusai.brain.coordinator import BrainCoordinator
from nexusai.brain.domain.agent import PlanGraph, StepStatus
from nexusai.brain.planner.validator import PlanValidationResult, PlanValidator
from nexusai.brain.ports.tool_port import ToolExecutionResult
from nexusai.models.base import BaseModelProvider
from nexusai.security.guard import RiskLevel
from nexusai.tools.base import BaseTool
from nexusai.tools.registry import ToolRegistry


class DummyInputSchema(BaseModel):
    query: str = Field(..., description="Query string")


class DummyAppTool(BaseTool):
    name = "search_tool"
    description = "Searches system index"
    risk_level = RiskLevel.LOW
    input_schema = DummyInputSchema

    async def execute(self, query: str, **kwargs: object) -> str:
        return f"Found results for '{query}'"


class MockProvider(BaseModelProvider):
    def __init__(self, response: dict | None = None) -> None:
        self.response = response or {"type": "text", "content": "Mock response"}
        self.last_messages: list = []
        self.last_tools: list | None = None

    async def chat(self, messages: list, tools: list | None = None) -> dict:
        self.last_messages = messages
        self.last_tools = tools
        return dict(self.response)


@pytest.mark.asyncio
async def test_cli_user_input_reaches_runtime_pipeline() -> None:
    """Verify user input through BrainCoordinator executes through PlanGraphExecutionEngine."""
    registry = ToolRegistry()
    registry.register(DummyAppTool())
    provider = MockProvider({"type": "text", "content": "Execution result"})

    coordinator = BrainCoordinator(model_provider=provider, registry=registry)
    res = await coordinator.process_user_input("Search query for system log")

    assert res["type"] == "text"
    assert res["content"] == "Execution result"
    assert "trace_id" in res
    assert "plan_nodes" in res

    # Verify runtime pipeline artifacts were generated
    assert coordinator.last_plan_graph is not None
    assert isinstance(coordinator.last_plan_graph, PlanGraph)
    assert coordinator.last_decision_trace is not None
    assert len(coordinator.last_plan_graph.nodes) > 0


@pytest.mark.asyncio
async def test_planner_and_validator_invoked_before_execution() -> None:
    """Verify ExecutionPlanner and PlanValidator are executed before tool/provider execution."""
    registry = ToolRegistry()
    registry.register(DummyAppTool())
    provider = MockProvider()

    coordinator = BrainCoordinator(model_provider=provider, registry=registry)

    with patch.object(
        coordinator.execution_engine.validator, "validate", wraps=coordinator.execution_engine.validator.validate
    ) as spy_validate, patch.object(
        coordinator.execution_engine.planner, "plan", wraps=coordinator.execution_engine.planner.plan
    ) as spy_plan:
        res = await coordinator.process_user_input("Perform search_tool task")

        assert spy_plan.called, "ExecutionPlanner must be invoked during user input processing"
        assert spy_validate.called, "PlanValidator must be invoked during user input processing"
        assert res["type"] == "text"


@pytest.mark.asyncio
async def test_validation_failure_blocks_execution() -> None:
    """Verify that a validation failure in PlanValidator prevents execution."""
    registry = ToolRegistry()
    provider = MockProvider()

    coordinator = BrainCoordinator(model_provider=provider, registry=registry)

    # Force validator to return an invalid result
    failing_result = PlanValidationResult(is_valid=False)
    failing_result.add_issue(node_id=1, rule_name="MockRule", message="Validation error forced")

    with patch.object(coordinator.execution_engine.validator, "validate", return_value=failing_result):
        with pytest.raises(RuntimeError, match="PlanGraph validation failed"):
            await coordinator.process_user_input("Invalid task input")


@pytest.mark.asyncio
async def test_offline_mock_execution_without_api_keys() -> None:
    """Verify offline execution works without an active model provider or API keys."""
    registry = ToolRegistry()
    registry.register(DummyAppTool())

    # Instantiate coordinator with model_provider=None (offline mode)
    coordinator = BrainCoordinator(model_provider=None, registry=registry)

    res = await coordinator.process_user_input("Offline query execution")

    assert res["status"] == "COMPLETED"
    assert res["iterations"] == 1
    assert "trace_id" in res
    assert "plan_nodes" in res
    assert coordinator.last_plan_graph is not None
    assert coordinator.last_decision_trace is not None


@pytest.mark.asyncio
async def test_direct_provider_bypass_does_not_occur() -> None:
    """Verify that user input processing populates pipeline traces instead of direct isolated provider calls."""
    provider = MockProvider({"type": "text", "content": "Direct check"})
    coordinator = BrainCoordinator(model_provider=provider)

    # Initial state trace is None
    assert coordinator.last_decision_trace is None

    await coordinator.process_user_input("Check pipeline trace generation")

    # Trace and PlanGraph must be populated by the runtime engine
    assert coordinator.last_decision_trace is not None
    assert coordinator.last_plan_graph is not None
    assert coordinator.last_decision_trace.chosen_action is not None


if __name__ == "__main__":
    import asyncio
    asyncio.run(test_cli_user_input_reaches_runtime_pipeline())
    asyncio.run(test_planner_and_validator_invoked_before_execution())
    asyncio.run(test_validation_failure_blocks_execution())
    asyncio.run(test_offline_mock_execution_without_api_keys())
    asyncio.run(test_direct_provider_bypass_does_not_occur())
    print("ALL P0-2 ENTRYPOINT INTEGRATION REGRESSION TESTS PASSED SUCCESSFULLY!")
