"""Observation Lifecycle States and ObservationMetadata container for NexusAI Brain Runtime."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from nexusai.core.errors import BrainContextAssemblyError


class LifecycleState(str, Enum):
    """Simplified 3-State Observation Lifecycle.

    States:
        ACTIVE: Active observation present in working context.
        COMPACTED: Observation summarized into context summary block.
        ARCHIVED: Observation moved out of working memory into long-term history.
    """

    ACTIVE = "ACTIVE"
    COMPACTED = "COMPACTED"
    ARCHIVED = "ARCHIVED"


class InvalidLifecycleTransitionError(BrainContextAssemblyError):
    """Raised when an illegal observation lifecycle state transition is attempted."""

    def __init__(self, current_state: LifecycleState, target_state: LifecycleState) -> None:
        super().__init__(
            f"Invalid ObservationMetadata lifecycle transition: '{current_state.value}' -> '{target_state.value}'"
        )
        self.current_state = current_state
        self.target_state = target_state


@dataclass
class ObservationMetadata:
    """Runtime-only metadata container associated with a pure Observation domain entity.

    Decoupled from the pure Observation domain entity to preserve domain immutability.

    Attributes:
        observation_id: Matching Observation.id UUID string.
        state: LifecycleState enum value (default ACTIVE).
        is_important: Metadata flag indicating high retention priority.
        importance_score: Calculated numerical score between 0.0 and 1.0.
    """

    observation_id: str
    state: LifecycleState = LifecycleState.ACTIVE
    is_important: bool = False
    importance_score: float = 0.0

    ALLOWED_TRANSITIONS: dict[LifecycleState, set[LifecycleState]] = {
        LifecycleState.ACTIVE: {LifecycleState.COMPACTED, LifecycleState.ARCHIVED},
        LifecycleState.COMPACTED: {LifecycleState.ARCHIVED},
        LifecycleState.ARCHIVED: set(),
    }

    def can_transition_to(self, target_state: LifecycleState) -> bool:
        """Check if lifecycle transition to target state is legal."""
        if target_state == self.state:
            return True
        allowed = self.ALLOWED_TRANSITIONS.get(self.state, set())
        return target_state in allowed

    def transition_to(self, target_state: LifecycleState) -> None:
        """Perform validated lifecycle state transition."""
        if not self.can_transition_to(target_state):
            raise InvalidLifecycleTransitionError(self.state, target_state)
        self.state = target_state

    def mark_compacted(self) -> None:
        """Transition state to COMPACTED."""
        self.transition_to(LifecycleState.COMPACTED)

    def mark_archived(self) -> None:
        """Transition state to ARCHIVED."""
        self.transition_to(LifecycleState.ARCHIVED)
