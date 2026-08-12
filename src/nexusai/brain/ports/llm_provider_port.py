"""ILLMProvider protocol contract interface for vendor-neutral LLM providers."""

from __future__ import annotations

from typing import Protocol

from nexusai.brain.domain.llm import LLMRequest, LLMResponse


class ILLMProvider(Protocol):
    """Abstract port interface isolating LLM model completions from vendor SDKs and wire formats."""

    @property
    def provider_name(self) -> str:
        """Return unique provider identifier (e.g. 'openai', 'anthropic', 'mock')."""
        ...

    async def complete(self, request: LLMRequest) -> LLMResponse:
        """Execute model completion request and return normalized LLMResponse.

        Must translate vendor SDK exceptions into LLMError taxonomy.
        MUST NOT perform hidden application-level retries (delegated to RecoveryPolicyEngine).
        """
        ...
