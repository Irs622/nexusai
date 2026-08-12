"""LLMProviderRegistry runtime implementation for thread-safe provider resolution."""

from __future__ import annotations

import asyncio
from typing import Any

from nexusai.brain.domain.llm import LLMProviderUnavailableError
from nexusai.brain.ports.llm_provider_port import ILLMProvider
from nexusai.brain.ports.llm_provider_registry_port import ILLMProviderRegistry
from nexusai.brain.ports.observability_port import IObservabilityPort


class LLMProviderRegistry(ILLMProviderRegistry):
    """Thread and coroutine safe LLMProviderRegistry enforcing unique provider registration and deterministic resolution."""

    def __init__(
        self,
        telemetry: IObservabilityPort | None = None,
    ) -> None:
        self.telemetry = telemetry
        self._lock = asyncio.Lock()
        self._providers: dict[str, ILLMProvider] = {}

    async def register(self, provider: ILLMProvider) -> None:
        """Register an ILLMProvider instance. Rejects duplicate provider_names."""
        name = provider.provider_name.lower().strip()
        async with self._lock:
            if name in self._providers:
                raise ValueError(f"Provider '{name}' is already registered in registry")
            self._providers[name] = provider

    async def resolve(self, provider_name: str) -> ILLMProvider:
        """Resolve a registered provider by name. Raises LLMProviderUnavailableError if unknown."""
        name = provider_name.lower().strip()
        async with self._lock:
            provider = self._providers.get(name)

        if provider is None:
            raise LLMProviderUnavailableError(f"Provider '{provider_name}' is not registered in registry")
        return provider

    async def list_providers(self) -> tuple[str, ...]:
        """List all registered provider names."""
        async with self._lock:
            names = sorted(list(self._providers.keys()))
        return tuple(names)
