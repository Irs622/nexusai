"""Domain models for P3-1 Agent Runtime, Execution States, Requests, and Responses."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import time
from typing import Any, Mapping

from nexusai.brain.domain.agent import DecisionTrace, PlanGraph
from nexusai.brain.ports.tool_port import ToolExecutionResult


class AgentExecutionState(str, Enum):
    """Lifecycle state machine for high-level Agent operations."""

    INITIALIZING = "INITIALIZING"
    PLANNING = "PLANNING"
    PLAN_VALIDATION = "PLAN_VALIDATION"
    GOVERNED_EXECUTION = "GOVERNED_EXECUTION"
    RECONCILING = "RECONCILING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True)
class AgentRequest:
    """Immutable user request submitted to IAgentRuntime."""

    session_id: str
    user_prompt: str
    agent_id: str = "default_agent"
    max_iterations: int = 10
    execution_timeout_seconds: float = 300.0
    constraints: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate request domain invariants."""
        if not self.session_id.strip():
            raise ValueError("session_id cannot be empty")
        if not self.user_prompt.strip():
            raise ValueError("user_prompt cannot be empty")
        if self.max_iterations <= 0:
            raise ValueError("max_iterations must be greater than 0")
        if self.execution_timeout_seconds <= 0.0:
            raise ValueError("execution_timeout_seconds must be greater than 0.0")


@dataclass(frozen=True)
class AgentResponse:
    """Immutable output response returned from IAgentRuntime."""

    session_id: str
    execution_id: str
    state: AgentExecutionState
    final_output: str
    plan_graph: PlanGraph | None = None
    results: tuple[ToolExecutionResult, ...] = field(default_factory=tuple)
    decision_trace: DecisionTrace | None = None
    duration_ms: float = 0.0
