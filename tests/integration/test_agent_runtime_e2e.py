"""End-to-End Integration Test for Multi-Turn Agent Runtime.

Validates complete integration across Planner -> Pipeline -> Provider -> Tool -> Observation -> Reflection -> Decision -> Persistence.
"""

from __future__ import annotations

import asyncio
from uuid import uuid4

from nexusai.brain.builder import AgentRuntimeBuilder
from nexusai.brain.domain.agent import AgentGoal, PlanStep, StepStatus
from nexusai.brain.domain.session import BrainSession
from nexusai.brain.pipeline.pipeline import ExecutionPipeline
from nexusai.brain.runtime.agent_context import AgentRuntimeContext
from nexusai.brain.runtime.state import SessionState
from nexusai.brain.state_machine import AgentState
from nexusai.brain.strategy import IPlanningStrategy, RuleDecisionStrategy, RuleReflectionStrategy
from nexusai.tools.adapter import ToolRegistryAdapter
from nexusai.tools.registry import ToolRegistry


class E2EFileReadTool:
    """Sample duck-typed tool reading workspace config."""

    name = "workspace_read_file"
    description = "Read workspace config file"

    def execute(self, file_path: str = "pyproject.toml") -> str:
        return f"File content of {file_path}: [project] name='nexusai'"

    def to_json_schema(self) -> dict[str, str]:
        return {"name": self.name, "description": self.description}


class E2EWorkspaceListTool:
    """Sample duck-typed tool listing directory."""

    name = "workspace_list_directory"
    description = "List directory contents"

    def execute(self, path: str = ".") -> list[str]:
        return ["pyproject.toml", "src", "tests", "docs"]

    def to_json_schema(self) -> dict[str, str]:
        return {"name": self.name, "description": self.description}


class MultiStepE2EPlanner(IPlanningStrategy):
    """Planner producing realistic multi-step plan for end-to-end testing."""

    async def generate_plan(self, goal: AgentGoal, ctx: AgentRuntimeContext) -> list[PlanStep]:
        return [
            PlanStep(
                step_id=1,
                title="List Directory",
                description="List files in root directory",
                tool_name="workspace_list_directory",
                arguments={"path": "."},
            ),
            PlanStep(
                step_id=2,
                title="Read Pyproject",
                description="Read configuration file",
                tool_name="workspace_read_file",
                arguments={"file_path": "pyproject.toml"},
            ),
        ]


def test_agent_runtime_end_to_end_full_flow():
    """Verify full end-to-end multi-turn execution flow across all core stages."""
    session = BrainSession(session_id=uuid4(), conversation_id=uuid4())
    goal = AgentGoal(description="Analyze workspace configuration")
    state = SessionState(provider_id="mock", active_model="mock-v1")

    # 1. Setup ToolRegistry with real tool capabilities
    registry = ToolRegistry()
    registry.register(E2EWorkspaceListTool())  # type: ignore[arg-type]
    registry.register(E2EFileReadTool())       # type: ignore[arg-type]
    tool_port = ToolRegistryAdapter(registry)

    # 2. Assemble AgentRuntimeFacade using AgentRuntimeBuilder
    builder = AgentRuntimeBuilder()
    builder.with_planning_strategy(MultiStepE2EPlanner())
    builder.with_reflection_strategy(RuleReflectionStrategy())
    builder.with_decision_strategy(RuleDecisionStrategy())
    builder.with_tool_port(tool_port)
    builder.with_pipeline(ExecutionPipeline())

    facade = builder.build()

    # 3. Execute multi-turn session
    response = asyncio.run(facade.run_agent_session(session, goal, state))

    # 4. Assert full flow compliance
    assert response.session_id == session.session_id
    assert response.final_state == AgentState.FINISHED
    assert len(response.working_memory.steps) == 2
    assert response.working_memory.steps[0].status == StepStatus.COMPLETED
    assert response.working_memory.steps[1].status == StepStatus.COMPLETED
    assert len(response.working_memory.observations) == 2

    # Verify observation contents mapped correctly from tools
    obs1 = response.working_memory.observations[0]
    obs2 = response.working_memory.observations[1]

    assert obs1.tool_name == "workspace_list_directory"
    assert obs1.success is True
    assert isinstance(obs1.payload, list)

    assert obs2.tool_name == "workspace_read_file"
    assert obs2.success is True
    assert "nexusai" in str(obs2.payload)

    # Verify metrics finalized
    assert response.metrics is not None


if __name__ == "__main__":
    test_agent_runtime_end_to_end_full_flow()
    print("END-TO-END MULTI-TURN AGENT RUNTIME TEST PASSED SUCCESSFULLY!")
