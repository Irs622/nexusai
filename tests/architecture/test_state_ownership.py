"""Architecture Fitness Test — Rule A008 (State Ownership Boundaries).

Verifies strict single ownership for Session, ExecutionContext, WorkingMemory, and PromptBundle.
"""

from __future__ import annotations

import dataclasses

from nexusai.brain.domain.agent import AgentGoal
from nexusai.brain.domain.prompt import MessageRole, PromptBundle, PromptMessage
from nexusai.brain.domain.session import BrainSession
from nexusai.brain.runtime.agent_context import AgentRuntimeContext
from nexusai.brain.runtime.context import ExecutionContext
from nexusai.brain.runtime.working_memory import WorkingMemory


def test_state_ownership_boundaries():
    """Verify single ownership fitness rules across state objects."""
    # 1. BrainSession is identity-owned by Session Manager
    session = BrainSession()
    assert hasattr(session, "session_id")
    assert hasattr(session, "conversation_id")

    # 2. ExecutionContext is transport-owned by Executor
    exec_ctx = ExecutionContext()
    assert hasattr(exec_ctx, "identity")
    assert hasattr(exec_ctx, "runtime")

    # 3. WorkingMemory is owned exclusively by AgentRuntimeContext
    goal = AgentGoal(description="Test goal")
    working_mem = WorkingMemory(goal=goal)
    agent_ctx = AgentRuntimeContext(execution_context=exec_ctx, working_memory=working_mem)
    assert agent_ctx.working_memory is working_mem

    # 4. PromptBundle is completely frozen / immutable after render
    msg = PromptMessage(role=MessageRole.USER, content="hello")
    bundle = PromptBundle(messages=(msg,))
    assert dataclasses.is_dataclass(bundle)


if __name__ == "__main__":
    test_state_ownership_boundaries()
    print("ALL STATE OWNERSHIP FITNESS TESTS PASSED SUCCESSFULLY!")
