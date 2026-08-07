"""
ContextTruncator service applying single-pass O(n) token window truncation strategies.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from nexusai.brain.domain.context import ContextBudget
from nexusai.brain.domain.prompt import MessageRole, PromptMessage
from nexusai.brain.domain.turn import Turn


class ITruncationStrategy(ABC):
    """Abstract truncation strategy interface."""

    @abstractmethod
    def truncate_turns(
        self,
        turns: tuple[Turn, ...],
        budget: ContextBudget,
    ) -> tuple[tuple[PromptMessage, ...], int]:
        """Truncate turns according to strategy constraints.

        Args:
            turns: Chronological tuple of Turn aggregate entities.
            budget: Target ContextBudget.

        Returns:
            Tuple of (truncated PromptMessage tuple, truncated_turn_count).
        """
        ...


class KeepLatestStrategy(ITruncationStrategy):
    """Default strategy preserving most recent history turns in single O(n) pass."""

    def truncate_turns(
        self,
        turns: tuple[Turn, ...],
        budget: ContextBudget,
    ) -> tuple[tuple[PromptMessage, ...], int]:
        """Truncate turns keeping most recent items."""
        available = budget.available_history_tokens
        accumulated_tokens = 0
        selected_messages: list[PromptMessage] = []
        truncated_count = 0

        # Process turns in reverse (most recent first)
        for turn in reversed(turns):
            user_tokens = len(turn.user_message.content) // 4 + 4
            asst_tokens = (
                len(turn.assistant_message.content) // 4 + 4
                if turn.assistant_message and turn.assistant_message.content
                else 0
            )
            turn_total = user_tokens + asst_tokens

            if accumulated_tokens + turn_total <= available:
                selected_messages.append(
                    PromptMessage(role=MessageRole.USER, content=turn.user_message.content)
                )
                if turn.assistant_message and turn.assistant_message.content:
                    selected_messages.append(
                        PromptMessage(role=MessageRole.ASSISTANT, content=turn.assistant_message.content)
                    )
                accumulated_tokens += turn_total
            else:
                truncated_count += 1

        # Re-reverse to restore chronological order
        selected_messages.reverse()
        return tuple(selected_messages), truncated_count


class ContextTruncator:
    """ContextTruncator service delegating to an ITruncationStrategy."""

    def __init__(self, strategy: ITruncationStrategy | None = None) -> None:
        """Initialize ContextTruncator with an ITruncationStrategy.

        Args:
            strategy: Strategy implementation (defaults to KeepLatestStrategy).
        """
        self._strategy = strategy or KeepLatestStrategy()

    def truncate_turns(
        self,
        turns: tuple[Turn, ...],
        budget: ContextBudget,
    ) -> tuple[tuple[PromptMessage, ...], int]:
        """Truncate history turns using active strategy."""
        return self._strategy.truncate_turns(turns, budget)
