"""ILLMProviderRegistry protocol contract for resolving vendor-neutral LLM Providers."""

from __future__ import annotations

from typing import Protocol

from nexusai.brain.ports.llm_provider_port import ILLMProvider


class ILLMProviderRegistry(Protocol):
    """Abstract port for registering and resolving vendor-neutral LLM providers."""

    async def register(self, provider: ILLMProvider) -> None:
        """Register an ILLMProvider instance. Rejects duplicate provider_names."""
        ...

    async def resolve(self, provider_name: str) -> ILLMProvider:
        """Resolve a registered provider by name. Raises LLMProviderUnavailableError if unknown."""
        ...

    async def list_providers(self) -> tuple[str, ...]:
        """List all registered provider names."""
        ...
