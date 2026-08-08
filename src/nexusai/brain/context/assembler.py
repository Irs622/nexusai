"""
ContextAssembler orchestrator service constructing AssembledContext value objects.
"""

from __future__ import annotations

from uuid import UUID

from nexusai.brain.context.history_loader import HistoryLoader
from nexusai.brain.context.system_prompt_resolver import SystemPromptResolver
from nexusai.brain.context.truncator import ContextTruncator
from nexusai.brain.domain.context import AssembledContext, ContextBudget
from nexusai.brain.domain.history import IHistoryProvider
from nexusai.brain.domain.prompt import MessageRole, PromptMessage
from nexusai.logging.logger import logger


class ContextAssembler:
    """Orchestrates history loading, system prompt resolution, and truncation into AssembledContext."""

    def __init__(
        self,
        history_provider: IHistoryProvider | None = None,
        history_loader: HistoryLoader | None = None,
        system_prompt_resolver: SystemPromptResolver | None = None,
        context_truncator: ContextTruncator | None = None,
    ) -> None:
        """Initialize ContextAssembler with component dependencies."""
        self._history_loader = history_loader or HistoryLoader(history_provider=history_provider)
        self._system_resolver = system_prompt_resolver or SystemPromptResolver()
        self._truncator = context_truncator or ContextTruncator()

    async def assemble(
        self,
        conversation_id: UUID,
        user_content: str,
        budget: ContextBudget,
        turn_system_override: str | None = None,
        session_system_default: str | None = None,
    ) -> AssembledContext:
        """Assemble context window for a turn request.

        Args:
            conversation_id: Target conversation UUID.
            user_content: Current incoming user prompt text.
            budget: Context token budget limits.
            turn_system_override: Optional system prompt passed in TurnRequest.
            session_system_default: Optional default system prompt from SessionState.

        Returns:
            An immutable AssembledContext payload.
        """
        logger.debug(f"Assembling context for conversation '{conversation_id}'")

        # 1. Resolve active system prompt
        system_instruction = self._system_resolver.resolve(
            turn_override=turn_system_override,
            session_default=session_system_default,
        )

        # 2. Fetch token-bounded history turns
        bounded_history = await self._history_loader.load_history(conversation_id, budget)

        # 3. Truncate history messages to fit within available token budget
        history_messages, truncated_count = self._truncator.truncate_turns(
            bounded_history.turns, budget
        )

        # 4. Construct current user prompt message
        user_message = PromptMessage(role=MessageRole.USER, content=user_content)

        # 5. Estimate total tokens
        system_tokens = len(system_instruction) // 4 + 4
        user_tokens = len(user_content) // 4 + 4
        history_tokens = sum(len(m.content) // 4 + 4 for m in history_messages)
        total_estimated = system_tokens + user_tokens + history_tokens

        return AssembledContext(
            system_instruction=system_instruction,
            history_messages=history_messages,
            user_message=user_message,
            estimated_total_tokens=total_estimated,
            truncated_turn_count=truncated_count + bounded_history.truncated_turn_count,
        )
