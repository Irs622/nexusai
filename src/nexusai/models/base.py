"""
Abstract Base Class for Model Providers in NexusAI.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseModelProvider(ABC):
    """Abstract Base Class enforced for all model providers (OpenAI, Claude, Ollama, etc.)."""

    @abstractmethod
    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Send chat messages and tool definitions to the LLM model.

        Args:
            messages: List of message objects (role, content, etc.)
            tools: Optional list of OpenAI-formatted tool JSON schemas

        Returns:
            Standardized response dictionary:
            - Plain text response: {"type": "text", "content": "..."}
            - Tool call response: {"type": "tool_call", "tool_name": "...", "arguments": {...}}
        """
        ...
