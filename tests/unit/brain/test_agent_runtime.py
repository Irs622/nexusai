"""Unit test suite for P3-1 Agent Runtime domain models, AgentRequest validation, and facade boundaries."""

from __future__ import annotations

import pytest

from nexusai.brain.domain.agent_runtime import (
    AgentExecutionState,
    AgentRequest,
    AgentResponse,
)
from nexusai.brain.runtime.brain_runtime_facade import BrainRuntimeFacade


def test_agent_request_domain_validation() -> None:
    """Test AgentRequest domain validation rules."""
    req = AgentRequest(session_id="sess-1", user_prompt="Execute task")
    assert req.session_id == "sess-1"
    assert req.user_prompt == "Execute task"
    assert req.max_iterations == 10

    # Invariant checks: Empty session_id or user_prompt rejected
    with pytest.raises(ValueError, match="session_id cannot be empty"):
        AgentRequest(session_id="  ", user_prompt="Execute task")

    with pytest.raises(ValueError, match="user_prompt cannot be empty"):
        AgentRequest(session_id="sess-1", user_prompt="  ")

    with pytest.raises(ValueError, match="max_iterations must be greater than 0"):
        AgentRequest(session_id="sess-1", user_prompt="Execute task", max_iterations=0)

    with pytest.raises(ValueError, match="execution_timeout_seconds must be greater than 0.0"):
        AgentRequest(session_id="sess-1", user_prompt="Execute task", execution_timeout_seconds=-5.0)


def test_agent_response_immutability() -> None:
    """Test AgentResponse dataclass immutability and final output separation."""
    resp = AgentResponse(
        session_id="sess-1",
        execution_id="exec-100",
        state=AgentExecutionState.COMPLETED,
        final_output="Synthesized Agent Answer",
    )

    assert resp.session_id == "sess-1"
    assert resp.execution_id == "exec-100"
    assert resp.final_output == "Synthesized Agent Answer"

    with pytest.raises(AttributeError):
        resp.final_output = "Mutated Output"  # type: ignore[misc]


if __name__ == "__main__":
    test_agent_request_domain_validation()
    test_agent_response_immutability()
    print("ALL P3-1 AGENT RUNTIME UNIT TESTS PASSED SUCCESSFULLY!")
