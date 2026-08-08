"""Acceptance Test Suite verifying complete End-to-End AI OS behavior runtime."""

import pytest

from nexusai.brain.agent_loop import AutonomousAgentLoop
from nexusai.brain.budget import ResourceBudgetEngine
from nexusai.domain.models import AgentSession, AgentState, BudgetPolicy, Goal


@pytest.mark.asyncio
async def test_full_autonomous_agent_loop_happy_path() -> None:
    """Test full End-to-End pipeline execution from Goal to FINISHED."""
    loop = AutonomousAgentLoop()

    hook_calls = []
    loop.register_hook("before_plan", lambda ctx: hook_calls.append("before_plan"))
    loop.register_hook("after_plan", lambda ctx: hook_calls.append("after_plan"))
    loop.register_hook("before_finish", lambda ctx: hook_calls.append("before_finish"))

    session = AgentSession()
    goal = Goal(prompt="Build Next.js Todo Application")

    final_context = await loop.run_session(session, goal)

    assert final_context.current_state == AgentState.FINISHED
    assert final_context.tool_calls_count == 2
    assert len(session.history) == 2
    assert hook_calls == ["before_plan", "after_plan", "before_finish"]


@pytest.mark.asyncio
async def test_agent_loop_budget_waiting_decision() -> None:
    """Test budget engine triggering WAITING state when retry count exceeded."""
    policy = BudgetPolicy(max_retries=0)
    budget_engine = ResourceBudgetEngine(policy)
    loop = AutonomousAgentLoop(budget_engine=budget_engine)

    session = AgentSession()
    goal = Goal(prompt="Execute high-risk action")

    final_context = await loop.run_session(session, goal)
    assert final_context.current_state == AgentState.WAITING
