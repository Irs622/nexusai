"""Runtime State Machine for tracking task execution states."""

from __future__ import annotations

from enum import Enum
from typing import Callable

from nexusai.core.annotations import stable
from nexusai.logging.logger import logger
from nexusai.providers.exceptions import ProviderSDKError


@stable
class ExecutionState(str, Enum):
    """Enumeration of explicit task execution states."""

    CREATED = "created"
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_TOOL = "waiting_tool"
    RETRYING = "retrying"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# Allowed state transitions graph
VALID_TRANSITIONS: dict[ExecutionState, set[ExecutionState]] = {
    ExecutionState.CREATED: {
        ExecutionState.QUEUED,
        ExecutionState.RUNNING,
        ExecutionState.CANCELLED,
    },
    ExecutionState.QUEUED: {ExecutionState.RUNNING, ExecutionState.CANCELLED},
    ExecutionState.RUNNING: {
        ExecutionState.WAITING_TOOL,
        ExecutionState.RETRYING,
        ExecutionState.COMPLETED,
        ExecutionState.FAILED,
        ExecutionState.CANCELLED,
    },
    ExecutionState.WAITING_TOOL: {
        ExecutionState.RUNNING,
        ExecutionState.FAILED,
        ExecutionState.CANCELLED,
    },
    ExecutionState.RETRYING: {
        ExecutionState.RUNNING,
        ExecutionState.FAILED,
        ExecutionState.CANCELLED,
    },
    ExecutionState.COMPLETED: set(),
    ExecutionState.FAILED: set(),
    ExecutionState.CANCELLED: set(),
}


@stable
class ExecutionStateMachine:
    """State machine governing valid task state transitions."""

    def __init__(self, initial_state: ExecutionState = ExecutionState.CREATED) -> None:
        self._current_state = initial_state
        self._listeners: list[Callable[[ExecutionState, ExecutionState], None]] = []

    @property
    def current_state(self) -> ExecutionState:
        """Get current task state."""
        return self._current_state

    def add_listener(self, listener: Callable[[ExecutionState, ExecutionState], None]) -> None:
        """Register a transition listener callback."""
        self._listeners.append(listener)

    def transition_to(self, new_state: ExecutionState, reason: str = "") -> None:
        """Transition task to a new state if valid.

        Args:
            new_state: Destination ExecutionState.
            reason: Optional explanation.

        Raises:
            ProviderSDKError: If transition is invalid.
        """
        allowed = VALID_TRANSITIONS.get(self._current_state, set())
        if new_state not in allowed:
            err_msg = f"Invalid state transition: {self._current_state.value} -> {new_state.value}"
            logger.error(err_msg)
            raise ProviderSDKError(err_msg)

        old_state = self._current_state
        self._current_state = new_state
        logger.info(
            "ExecutionState transition: {} -> {} ({})", old_state.value, new_state.value, reason
        )

        for listener in self._listeners:
            try:
                listener(old_state, new_state)
            except Exception as listener_err:
                logger.error("Error in ExecutionState transition listener: {}", listener_err)
