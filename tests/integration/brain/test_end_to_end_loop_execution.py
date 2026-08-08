"""Phase 4 P0 End-to-End Integration Test Suite.

Verifies full realistic multi-turn execution loops across:
LoopExecutor -> Planner -> Tool Execution -> Failure Handling -> Observation -> Importance Scoring -> Compaction -> Summary -> WorkingMemory.
"""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from loguru import logger

from nexusai.brain.builder import AgentRuntimeBuilder
from nexusai.brain.compaction.budget import ContextBudget
from nexusai.brain.compaction.importance import RetentionPolicy
from nexusai.brain.container import RuntimeDependencies
from nexusai.brain.domain.agent import AgentGoal, PlanStep, StepStatus
from nexusai.brain.domain.session import BrainSession
from nexusai.brain.failure_detector import FailureCategory, FailureEvidence, RuleFailureClassifier
from nexusai.brain.loop_executor import LoopExecutor
from nexusai.brain.ports.tool_port import IToolPort, ToolExecutionResult
from nexusai.brain.runtime.state import SessionState
from nexusai.brain.state_machine import AgentState
from nexusai.brain.telemetry.metrics import InMemoryMetricsCollector


@pytest.mark.asyncio
async def test_e2e_successful_multi_turn_execution_with_compaction():
    """E2E Integration Scenario: Successful multi-turn execution with automatic compaction and telemetry."""
    logger.disable("nexusai")
    collector = InMemoryMetricsCollector()
    budget = ContextBudget(max_units=60, warning_threshold_ratio=0.5)
    policy = RetentionPolicy(max_active_observations=1)

    deps = RuntimeDependencies(
        context_budget=budget,
        retention_policy=policy,
        metrics_collector=collector,
    )

    mock_tool_port = AsyncMock(spec=IToolPort)
    mock_tool_port.execute.return_value = ToolExecutionResult(
        tool_name="workspace_file_writer",
        success=True,
        result="File successfully written with detailed payload content " * 5,
    )

    executor = LoopExecutor(deps=deps, tool_port=mock_tool_port)

    facade = AgentRuntimeBuilder().build()
    facade._executor = executor

    session = BrainSession(session_id=uuid4(), conversation_id=uuid4())
    goal = AgentGoal(description="E2E multi-turn file creation goal")
    state = SessionState(provider_id="mock", active_model="mock-v1")

    agent_ctx = facade.create_agent_context(session=session, goal=goal, state=state)

    # Execute loop
    final_mem = await executor.execute_loop(agent_ctx)

    assert agent_ctx.state_machine.current_state in (AgentState.FINISHED, AgentState.DECISION)
    assert len(final_mem.observations) <= 2
    assert collector.snapshot().trigger_count >= 1
    assert collector.snapshot().summary_count >= 1


@pytest.mark.asyncio
async def test_e2e_failure_handling_timeout_and_retry():
    """E2E Integration Scenario: Tool execution timeout failure recording and retry policy tracking."""
    collector = InMemoryMetricsCollector()
    deps = RuntimeDependencies(metrics_collector=collector)

    mock_tool_port = AsyncMock(spec=IToolPort)
    mock_tool_port.execute.return_value = ToolExecutionResult(
        tool_name="http_request",
        success=False,
        error_message="HTTP request connection timeout",
    )

    executor = LoopExecutor(deps=deps, tool_port=mock_tool_port)
    facade = AgentRuntimeBuilder().build()
    facade._executor = executor

    session = BrainSession(session_id=uuid4(), conversation_id=uuid4())
    goal = AgentGoal(description="E2E timeout test goal")
    state = SessionState(provider_id="mock", active_model="mock-v1")

    agent_ctx = facade.create_agent_context(session=session, goal=goal, state=state)
    mem = agent_ctx.working_memory

    # Inject step requiring tool execution
    step = PlanStep(
        step_id=1, title="Fetch API", tool_name="http_request", status=StepStatus.RUNNING
    )
    mem.steps = [step]
    mem.current_step_index = 0

    await executor.execute_loop(agent_ctx)

    # Assert failure record created
    assert len(mem.failures) >= 1
    assert "timeout" in mem.failures[0].error_message.lower()


@pytest.mark.asyncio
async def test_e2e_failure_classification_permission_and_oscillation():
    """E2E Integration Scenario: FailureClassifier detects permission failure and tool oscillation patterns."""
    classifier = RuleFailureClassifier()

    # Permission Failure Scenario
    ev_perm = FailureEvidence(
        tool_name="write_root", error_message="Permission denied", http_status=403
    )
    analysis_perm = classifier.classify([ev_perm])
    assert analysis_perm is not None
    assert analysis_perm.category == FailureCategory.PERMISSION

    # Oscillation Loop Scenario (Tool A -> Tool B -> Tool A)
    ev1 = FailureEvidence(tool_name="read_config", error_message="Not found")
    ev2 = FailureEvidence(tool_name="fetch_default", error_message="Invalid key")
    ev3 = FailureEvidence(tool_name="read_config", error_message="Not found")

    analysis_osc = classifier.classify([ev1, ev2, ev3])
    assert analysis_osc is not None
    assert analysis_osc.category == FailureCategory.OSCILLATION
    assert "Oscillation loop detected" in analysis_osc.recommendation
