"""
HistoryLoader service delegating to IHistoryProvider port.
"""

from __future__ import annotations

from uuid import UUID

from nexusai.brain.domain.context import ContextBudget
from nexusai.brain.domain.history import IHistoryProvider, TokenBoundedHistory
from nexusai.brain.domain.turn import Turn
from nexusai.logging.logger import logger


class InMemoryHistoryProvider(IHistoryProvider):
    """In-memory reference implementation of IHistoryProvider for testing and fallback."""

    def __init__(self, turns: list[Turn] | None = None) -> None:
        self.turns = turns or []

    async def fetch_context(
        self,
        conversation_id: UUID,
        budget: ContextBudget,
    ) -> TokenBoundedHistory:
        """Fetch turns bounded by ContextBudget."""
        available_tokens = budget.available_history_tokens
        accumulated_tokens = 0
        selected_turns: list[Turn] = []
        truncated_count = 0

        # Iterate turns in reverse (most recent first)
        for turn in reversed(self.turns):
            turn_tokens = turn.token_usage.get("total", len(turn.user_message.content) // 4 + 10)
            if accumulated_tokens + turn_tokens <= available_tokens:
                selected_turns.append(turn)
                accumulated_tokens += turn_tokens
            else:
                truncated_count += 1

        # Re-reverse to restore chronological order
        selected_turns.reverse()
        return TokenBoundedHistory(
            turns=tuple(selected_turns),
            total_tokens=accumulated_tokens,
            truncated_turn_count=truncated_count,
        )


class HistoryLoader:
    """HistoryLoader service orchestrating token-bounded history retrieval."""

    def __init__(self, history_provider: IHistoryProvider | None = None) -> None:
        """Initialize HistoryLoader with an IHistoryProvider implementation.

        Args:
            history_provider: Port implementation (defaults to InMemoryHistoryProvider).
        """
        self._provider = history_provider or InMemoryHistoryProvider()

    async def load_history(
        self,
        conversation_id: UUID,
        budget: ContextBudget,
    ) -> TokenBoundedHistory:
        """Load history turns bounded by ContextBudget.

        Args:
            conversation_id: Target conversation UUID.
            budget: Token budget limits.

        Returns:
            TokenBoundedHistory container.
        """
        logger.bind(
            conversation_id=str(conversation_id),
            available_tokens=budget.available_history_tokens,
        ).debug("Loading history context")
        return await self._provider.fetch_context(conversation_id, budget)
