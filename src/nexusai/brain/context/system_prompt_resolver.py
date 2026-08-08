"""
SystemPromptResolver service resolving active system instruction hierarchy.
"""

from __future__ import annotations


class SystemPromptResolver:
    """Resolves active system prompt from global defaults, session defaults, and turn overrides."""

    DEFAULT_GLOBAL_SYSTEM_PROMPT = (
        "You are NexusAI, a helpful, precise AI Operating System assistant."
    )

    def resolve(
        self,
        turn_override: str | None = None,
        session_default: str | None = None,
        global_default: str | None = None,
    ) -> str:
        """Resolve active system prompt following precedence: turn_override > session_default > global_default.

        Args:
            turn_override: Optional system prompt passed in TurnRequest.
            session_default: Optional system prompt configured in BrainSession/SessionState.
            global_default: Optional global fallback system prompt.

        Returns:
            Resolved system prompt string.
        """
        if turn_override and turn_override.strip():
            return turn_override.strip()
        if session_default and session_default.strip():
            return session_default.strip()
        if global_default and global_default.strip():
            return global_default.strip()
        return self.DEFAULT_GLOBAL_SYSTEM_PROMPT
