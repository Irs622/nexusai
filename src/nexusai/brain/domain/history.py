"""
IHistoryProvider port interface and TokenBoundedHistory value object.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from nexusai.brain.domain.context import ContextBudget
from nexusai.brain.domain.turn import Turn


@dataclass(frozen=True)
class TokenBoundedHistory:
    """Immutable container for token-bounded history turns fetched from storage layer.

    Attributes:
        turns: Immutable tuple of fetched Turn aggregate entities.
        total_tokens: Total token count of the returned turns.
        truncated_turn_count: Number of older turns excluded by token budget bounds.
    """

    turns: tuple[Turn, ...] = field(default_factory=tuple)
    total_tokens: int = 0
    truncated_turn_count: int = 0

    def __post_init__(self) -> None:
        """Ensure turns list is converted to an immutable tuple."""
        if isinstance(self.turns, list):
            object.__setattr__(self, "turns", tuple(self.turns))

    def to_dict(self) -> dict[str, Any]:
        """Serialize TokenBoundedHistory to dictionary format."""
        return {
            "total_tokens": self.total_tokens,
            "truncated_turn_count": self.truncated_turn_count,
            "turn_count": len(self.turns),
        }


class IHistoryProvider(ABC):
    """Abstract port interface for fetching token-bounded conversation history."""

    @abstractmethod
    async def fetch_context(
        self,
        conversation_id: UUID,
        budget: ContextBudget,
    ) -> TokenBoundedHistory:
        """Fetch conversation history turns bounded by ContextBudget at the storage layer.

        Args:
            conversation_id: Target conversation UUID.
            budget: Token budget limits.

        Returns:
            TokenBoundedHistory containing bounded turns.
        """
        ...
