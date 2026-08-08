"""Provider Operational Manager for managing lifecycle, health, and capability queries."""

from __future__ import annotations

import asyncio

from nexusai.core.annotations import stable
from nexusai.logging.logger import logger
from nexusai.providers.base import BaseProvider
from nexusai.providers.models import Capability, CapabilityLevel, ProviderHealth
from nexusai.providers.registry import ProviderRegistry


@stable
class ProviderManager:
    """Operational lifecycle and health manager for registered provider adapters."""

    def __init__(self, registry: ProviderRegistry | None = None) -> None:
        self._registry = registry or ProviderRegistry()

    @property
    def registry(self) -> ProviderRegistry:
        """Access the underlying ProviderRegistry instance."""
        return self._registry

    async def initialize_all(self) -> None:
        """Initialize all registered providers asynchronously."""
        logger.info("Initializing all registered providers")
        for provider_id in self._registry.list_provider_ids():
            provider = self._registry.get(provider_id)
            await provider.initialize()

    async def shutdown_all(self) -> None:
        """Shutdown all registered providers asynchronously."""
        logger.info("Shutting down all registered providers")
        for provider_id in self._registry.list_provider_ids():
            provider = self._registry.get(provider_id)
            await provider.shutdown()

    async def health_check_all(self) -> dict[str, ProviderHealth]:
        """Perform health checks on all registered providers concurrently.

        Returns:
            Dictionary mapping provider_id to ProviderHealth snapshot.
        """
        logger.info("Executing health checks across all registered providers")
        provider_ids = self._registry.list_provider_ids()
        tasks = [self._registry.get(pid).health_check() for pid in provider_ids]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        health_map: dict[str, ProviderHealth] = {}
        for pid, res in zip(provider_ids, results):
            if isinstance(res, ProviderHealth):
                health_map[pid] = res
            elif isinstance(res, Exception):
                health_map[pid] = ProviderHealth(healthy=False, error=str(res))
            else:
                health_map[pid] = ProviderHealth(
                    healthy=False, error="Unknown health check failure"
                )

        return health_map

    def find_by_capability(
        self,
        capability: Capability,
        min_level: CapabilityLevel = CapabilityLevel.BASIC,
    ) -> list[BaseProvider]:
        """Find providers supporting a capability at or above a given level.

        Args:
            capability: Target Capability enum.
            min_level: Minimum required CapabilityLevel.

        Returns:
            List of BaseProvider instances matching capability requirements.
        """
        matches: list[BaseProvider] = []
        for pid in self._registry.list_provider_ids():
            p = self._registry.get(pid)
            if p.metadata.capabilities.supports(capability, min_level):
                matches.append(p)
        return matches

    def supports(
        self,
        provider_id: str,
        capability: Capability,
        min_level: CapabilityLevel = CapabilityLevel.BASIC,
    ) -> bool:
        """Check if a specific provider supports a capability.

        Args:
            provider_id: Identifier of provider.
            capability: Target Capability enum.
            min_level: Minimum required CapabilityLevel.

        Returns:
            True if supported, False otherwise.
        """
        p = self._registry.get(provider_id)
        return p.metadata.capabilities.supports(capability, min_level)

    async def healthy_providers(self) -> list[BaseProvider]:
        """Retrieve all currently healthy providers.

        Returns:
            List of BaseProvider instances that returned healthy status.
        """
        health_map = await self.health_check_all()
        healthy_list: list[BaseProvider] = []
        for pid, health in health_map.items():
            if health.healthy:
                healthy_list.append(self._registry.get(pid))
        return healthy_list
