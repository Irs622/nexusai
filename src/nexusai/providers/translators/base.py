"""Abstract Base Class for Vendor Payload Translators."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from nexusai.core.annotations import stable
from nexusai.providers.models import ChatRequest, ChatResponse, ToolCall


@stable
class BaseTranslator(ABC):
    """Abstract Base Class for translating between raw vendor API payloads and canonical SDK models."""

    @abstractmethod
    def from_canonical_request(self, request: ChatRequest) -> dict[str, Any]:
        """Translate a canonical ChatRequest into vendor-specific wire payload.

        Args:
            request: Canonical ChatRequest.

        Returns:
            Raw vendor dictionary.
        """
        ...

    @abstractmethod
    def to_canonical_response(self, raw_payload: dict[str, Any], provider_id: str) -> ChatResponse:
        """Translate a raw vendor payload into canonical ChatResponse.

        Args:
            raw_payload: Vendor wire response dictionary.
            provider_id: Unique provider identifier.

        Returns:
            Canonical ChatResponse instance.
        """
        ...

    @abstractmethod
    def normalize_tool_calls(self, raw_calls: Any) -> list[ToolCall]:
        """Normalize vendor tool call structures into canonical ToolCall models."""
        ...
