"""
Abstract Base Class for Memory Systems in NexusAI.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseMemory(ABC):
    """Abstract Base Class for session conversation memory."""

    @abstractmethod
    async def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        name: str | None = None,
    ) -> None:
        """Add a conversation message to session memory."""
        ...

    @abstractmethod
    async def get_messages(
        self,
        session_id: str,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Retrieve recent conversation history for a session."""
        ...

    @abstractmethod
    async def clear_session(self, session_id: str) -> None:
        """Clear all stored messages for a specific session."""
        ...
