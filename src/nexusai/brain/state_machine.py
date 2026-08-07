"""Pure AgentStateMachine transition validator for NexusAI Agent Runtime."""

from __future__ import annotations

from enum import Enum
from nexusai.logging.logger import logger


class AgentState(str, Enum):
    """10-State Autonomous Agent Lifecycle."""

    IDLE = "IDLE"
    PLANNING = "PLANNING"
    REASONING = "REASONING"
    TOOL_EXECUTION = "TOOL_EXECUTION"
    OBSERVING = "OBSERVING"
    REFLECTING = "REFLECTING"
    DECISION = "DECISION"
    REPLANNING = "REPLANNING"
    WAITING = "WAITING"
    FINISHED = "FINISHED"
    FAILED = "FAILED"


class InvalidStateTransitionError(Exception):
    """Raised when an illegal state machine transition is attempted."""

    def __init__(self, current_state: AgentState, target_state: AgentState) -> None:
        super().__init__(
            f"Invalid AgentStateMachine transition from '{current_state.value}' to '{target_state.value}'"
        )
        self.current_state = current_state
        self.target_state = target_state


class AgentStateMachine:
    """Pure, deterministic state machine validating 10-state agent transitions.

    Contains ZERO business logic, LLM calls, or side effects.
    """

    ALLOWED_TRANSITIONS: dict[AgentState, set[AgentState]] = {
        AgentState.IDLE: {AgentState.PLANNING, AgentState.FAILED},
        AgentState.PLANNING: {AgentState.REASONING, AgentState.FAILED},
        AgentState.REASONING: {
            AgentState.TOOL_EXECUTION,
            AgentState.DECISION,
            AgentState.WAITING,
            AgentState.FAILED,
            AgentState.FINISHED,
        },
        AgentState.TOOL_EXECUTION: {AgentState.OBSERVING, AgentState.FAILED},
        AgentState.OBSERVING: {AgentState.REFLECTING, AgentState.FAILED},
        AgentState.REFLECTING: {AgentState.DECISION, AgentState.FAILED},
        AgentState.DECISION: {
            AgentState.REASONING,
            AgentState.REPLANNING,
            AgentState.WAITING,
            AgentState.FINISHED,
            AgentState.FAILED,
        },
        AgentState.REPLANNING: {AgentState.PLANNING, AgentState.REASONING, AgentState.FAILED},
        AgentState.WAITING: {
            AgentState.REASONING,
            AgentState.TOOL_EXECUTION,
            AgentState.FINISHED,
            AgentState.FAILED,
        },
        AgentState.FINISHED: {AgentState.IDLE},
        AgentState.FAILED: {AgentState.IDLE},
    }

    def __init__(self, initial_state: AgentState = AgentState.IDLE) -> None:
        self._current_state = initial_state

    @property
    def current_state(self) -> AgentState:
        """Get current agent state."""
        return self._current_state

    def can_transition_to(self, target_state: AgentState) -> bool:
        """Check if transition from current state to target state is legal."""
        allowed = self.ALLOWED_TRANSITIONS.get(self._current_state, set())
        return target_state in allowed

    def transition_to(self, target_state: AgentState) -> None:
        """Perform validated state transition.

        Args:
            target_state: Desired destination AgentState.

        Raises:
            InvalidStateTransitionError: If transition is illegal.
        """
        if not self.can_transition_to(target_state):
            logger.error(
                f"Illegal state transition attempted: {self._current_state.value} -> {target_state.value}"
            )
            raise InvalidStateTransitionError(self._current_state, target_state)

        logger.debug(f"AgentStateMachine transitioned: {self._current_state.value} -> {target_state.value}")
        self._current_state = target_state
