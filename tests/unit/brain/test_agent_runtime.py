"""Comprehensive unit test suite for Phase 3.2 Agent Runtime components."""

from __future__ import annotations

import asyncio
from uuid import uuid4

from nexusai.brain.domain.agent import (
    AgentGoal,
    LoopDecision,
    PlanStep,
    ReflectionAnalysis,
    StepStatus,
)
from nexusai.brain.domain.session import BrainSession
from nexusai.brain.observation import ObservationMapper
from nexusai.brain.ports.tool_port import ToolExecutionRequest
from nexusai.brain.runtime.agent_context import AgentRuntimeContext
from nexusai.brain.runtime.context import ExecutionContext
from nexusai.brain.runtime.state import SessionState
from nexusai.brain.runtime.working_memory import RetryPolicy, WorkingMemory
from nexusai.brain.service import AgentRuntimeFacade
from nexusai.brain.state_machine import AgentState, AgentStateMachine, InvalidStateTransitionError
from nexusai.brain.strategy import (
    RuleDecisionStrategy,
    RulePlanningStrategy,
    RuleReflectionStrategy,
)
from nexusai.domain.models import Observation
from nexusai.tools.adapter import ToolRegistryAdapter
from nexusai.tools.registry import ToolRegistry


class SimpleMockTool:
    """Duck-typed test tool for registry testing without pydantic dependency."""

    name = "dummy_mock_tool"
    description = "Mock tool for unit tests"

    def execute(self, message: str = "hello") -> str:
        return f"Mocked: {message}"

    def to_json_schema(self) -> dict[str, str]:
        return {"name": self.name, "description": self.description}


def test_agent_state_machine_valid_transitions() -> None:
    """Verify valid transitions in AgentStateMachine."""
    sm = AgentStateMachine(AgentState.IDLE)
    assert sm.current_state == AgentState.IDLE

    sm.transition_to(AgentState.PLANNING)
    assert sm.current_state == AgentState.PLANNING

    sm.transition_to(AgentState.REASONING)
    assert sm.current_state == AgentState.REASONING

    sm.transition_to(AgentState.TOOL_EXECUTION)
    assert sm.current_state == AgentState.TOOL_EXECUTION

    sm.transition_to(AgentState.OBSERVING)
    assert sm.current_state == AgentState.OBSERVING

    sm.transition_to(AgentState.REFLECTING)
    assert sm.current_state == AgentState.REFLECTING

    sm.transition_to(AgentState.DECISION)
    assert sm.current_state == AgentState.DECISION

    sm.transition_to(AgentState.FINISHED)
    assert sm.current_state == AgentState.FINISHED


def test_agent_state_machine_invalid_transition_raises_error() -> None:
    """Verify invalid transition raises InvalidStateTransitionError."""
    sm = AgentStateMachine(AgentState.IDLE)
    raised = False
    try:
        sm.transition_to(AgentState.REFLECTING)
    except InvalidStateTransitionError:
        raised = True
    assert raised is True


def test_working_memory_step_indexing() -> None:
    """Verify single source of truth current_step resolution in WorkingMemory."""
    goal = AgentGoal(description="Test goal")
    step1 = PlanStep(step_id=1, title="Step 1", description="Desc 1")
    step2 = PlanStep(step_id=2, title="Step 2", description="Desc 2")

    mem = WorkingMemory(goal=goal, steps=[step1, step2])
    assert mem.current_step == step1
    assert mem.current_step_index == 0

    nxt = mem.advance_step()
    assert nxt == step2
    assert mem.current_step == step2
    assert step1.status == StepStatus.COMPLETED
    assert step2.status == StepStatus.RUNNING


def test_retry_policy() -> None:
    """Verify RetryPolicy evaluation logic."""
    policy = RetryPolicy(max_attempts=3)
    mem = WorkingMemory(goal=AgentGoal(description="Retry test"), retry_policy=policy)

    fail1 = mem.record_failure(step_id=1, error_message="NETWORK_ERROR timeout")
    assert policy.is_retryable(fail1, current_attempts=1) is True
    assert policy.is_retryable(fail1, current_attempts=3) is False


def test_rule_strategies() -> None:
    """Verify RulePlanningStrategy, RuleReflectionStrategy, and RuleDecisionStrategy."""
    goal = AgentGoal(description="Build feature")
    exec_ctx = ExecutionContext()
    working_mem = WorkingMemory(goal=goal)
    agent_ctx = AgentRuntimeContext(execution_context=exec_ctx, working_memory=working_mem)

    planner = RulePlanningStrategy()
    steps = asyncio.run(planner.generate_plan(goal, agent_ctx))
    assert len(steps) == 2
    assert steps[0].step_id == 1

    reflector = RuleReflectionStrategy()
    obs = Observation(source="tool", tool_name="test", success=True, payload="Success")
    analysis = asyncio.run(reflector.reflect(working_mem, obs))
    assert isinstance(analysis, ReflectionAnalysis)

    decider = RuleDecisionStrategy()
    decision = decider.decide(working_mem, analysis)
    assert decision in (
        LoopDecision.CONTINUE,
        LoopDecision.COMPLETE,
        LoopDecision.REPLAN,
        LoopDecision.FAIL,
    )


def test_tool_registry_adapter_and_observation_mapper() -> None:
    """Verify ToolRegistryAdapter and ObservationMapper integration."""
    registry = ToolRegistry()
    tool_inst = SimpleMockTool()  # type: ignore[arg-type]
    registry.register(tool_inst)  # type: ignore[arg-type]

    adapter = ToolRegistryAdapter(registry)
    req = ToolExecutionRequest(tool_name="dummy_mock_tool", arguments={"message": "world"})

    res = asyncio.run(adapter.execute(req))
    assert res.success is True
    assert res.output == "Mocked: world"

    mapper = ObservationMapper()
    obs = mapper.map_tool_result(res)
    assert obs.tool_name == "dummy_mock_tool"
    assert obs.success is True
    assert obs.metrics.get("execution_time_ms") is not None


def test_agent_runtime_facade_end_to_end() -> None:
    """Verify end-to-end multi-turn session execution using AgentRuntimeFacade."""
    session = BrainSession(session_id=uuid4(), conversation_id=uuid4())
    goal = AgentGoal(description="Automate task execution")
    state = SessionState(provider_id="mock", active_model="mock-v1")

    registry = ToolRegistry()
    tool_inst = SimpleMockTool()  # type: ignore[arg-type]
    registry.register(tool_inst)  # type: ignore[arg-type]
    tool_port = ToolRegistryAdapter(registry)

    facade = AgentRuntimeFacade(tool_port=tool_port)
    response = asyncio.run(facade.run_agent_session(session, goal, state))

    assert response.session_id == session.session_id
    assert response.final_state in (AgentState.FINISHED, AgentState.FAILED)
    assert len(response.working_memory.observations) > 0
    assert response.metrics is not None


if __name__ == "__main__":
    test_agent_state_machine_valid_transitions()
    test_agent_state_machine_invalid_transition_raises_error()
    test_working_memory_step_indexing()
    test_retry_policy()
    test_rule_strategies()
    test_tool_registry_adapter_and_observation_mapper()
    test_agent_runtime_facade_end_to_end()
    print("ALL AGENT RUNTIME UNIT TESTS PASSED SUCCESSFULLY!")
