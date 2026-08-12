"""Unit test suite for P3-4 AgentLoop state machine, configuration, plan fingerprinting, and deterministic outcome evaluation."""

from __future__ import annotations

import asyncio
import pytest

from nexusai.brain.domain.agent import PlanGraph, PlanGraphNode, PlanStep
from nexusai.brain.domain.agent_loop import (
    AgentLoopConfig,
    AgentLoopState,
    Observation,
    compute_plan_fingerprint,
)
from nexusai.brain.domain.agent_runtime import AgentRequest
from nexusai.brain.ports.tool_port import ToolExecutionResult
from nexusai.brain.runtime.deterministic_evaluator import DeterministicOutcomeEvaluator


def test_agent_loop_config_validation() -> None:
    """Test AgentLoopConfig domain validation rules."""
    config = AgentLoopConfig(max_iterations=10, max_replans=5)
    assert config.max_iterations == 10
    assert config.max_replans == 5

    with pytest.raises(ValueError, match="max_iterations must be greater than 0"):
        AgentLoopConfig(max_iterations=0)

    with pytest.raises(ValueError, match="max_replans cannot be negative"):
        AgentLoopConfig(max_replans=-1)


def test_plan_fingerprinting_determinism() -> None:
    """Test compute_plan_fingerprint produces identical canonical hash for structurally equivalent PlanGraphs."""
    nodes1 = {
        1: PlanGraphNode(step=PlanStep(step_id=1, title="A", tool_name="terminal"), dependencies=()),
        2: PlanGraphNode(step=PlanStep(step_id=2, title="B", tool_name="file_reader"), dependencies=(1,)),
    }
    graph1 = PlanGraph(nodes=nodes1, edges=((1, 2),))

    nodes2 = {
        2: PlanGraphNode(step=PlanStep(step_id=2, title="B", tool_name="file_reader"), dependencies=(1,)),
        1: PlanGraphNode(step=PlanStep(step_id=1, title="A", tool_name="terminal"), dependencies=()),
    }
    graph2 = PlanGraph(nodes=nodes2, edges=((1, 2),))

    hash1 = compute_plan_fingerprint(graph1)
    hash2 = compute_plan_fingerprint(graph2)

    assert hash1 == hash2, "Canonical plan graph fingerprints must match regardless of dict insertion order"


@pytest.mark.asyncio
async def test_deterministic_outcome_evaluator() -> None:
    """Test DeterministicOutcomeEvaluator evaluation decisions."""
    evaluator = DeterministicOutcomeEvaluator()
    req = AgentRequest(session_id="sess-eval", user_prompt="Prompt")
    config = AgentLoopConfig(max_replans=3, allow_replanning=True)

    # 1. All succeeded -> COMPLETED
    res_succ = ToolExecutionResult("r1", "tool1", success=True, output="Done")
    obs_succ = Observation("exec-1", 1, (res_succ,), 1, 0, 0, True, "Summary")
    dec_succ = await evaluator.evaluate(req, obs_succ, config, iteration=1, replan_count=0)
    assert dec_succ.action == "COMPLETED"

    # 2. 1 Failed & replan budget available -> REPLAN
    res_fail = ToolExecutionResult("r2", "tool2", success=False, error_message="Error")
    obs_fail = Observation("exec-1", 1, (res_fail,), 0, 1, 0, False, "Summary")
    dec_replan = await evaluator.evaluate(req, obs_fail, config, iteration=1, replan_count=1)
    assert dec_replan.action == "REPLAN"

    # 3. 1 Failed & replan budget exhausted -> FAILED
    dec_fail = await evaluator.evaluate(req, obs_fail, config, iteration=1, replan_count=3)
    assert dec_fail.action == "FAILED"


if __name__ == "__main__":
    test_agent_loop_config_validation()
    test_plan_fingerprinting_determinism()
    asyncio.run(test_deterministic_outcome_evaluator())
    print("ALL P3-4 AGENT LOOP UNIT TESTS PASSED SUCCESSFULLY!")
