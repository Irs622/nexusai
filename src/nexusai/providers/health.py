"""Dedicated Health Monitoring service for Provider SDK background monitoring."""

from __future__ import annotations

import asyncio
from typing import Callable

from nexusai.core.annotations import stable
from nexusai.logging.logger import logger
from nexusai.providers.models import ProviderHealth
from nexusai.providers.registry import ProviderRegistry


@stable
class HealthMonitor:
    """Dedicated background service for monitoring provider health status."""

    def __init__(self, registry: ProviderRegistry, interval_seconds: float = 60.0) -> None:
        self._registry = registry
        self._interval_seconds = interval_seconds
        self._health_map: dict[str, ProviderHealth] = {}
        self._running = False
        self._task: asyncio.Task[None] | None = None
        self._callbacks: list[Callable[[str, ProviderHealth], None]] = []

    def add_callback(self, callback: Callable[[str, ProviderHealth], None]) -> None:
        """Register a callback invoked when a provider health state is updated."""
        self._callbacks.append(callback)

    async def check_provider(self, provider_id: str) -> ProviderHealth:
        """Execute a health check on a specific registered provider.

        Args:
            provider_id: Identifier of target provider.

        Returns:
            ProviderHealth snapshot result.
        """
        try:
            provider = self._registry.get(provider_id)
            health = await provider.health_check()
        except Exception as err:
            logger.warning("Health check failed for '{}': {}", provider_id, err)
            health = ProviderHealth(healthy=False, error=str(err))

        self._health_map[provider_id] = health

        for cb in self._callbacks:
            try:
                cb(provider_id, health)
            except Exception as cb_err:
                logger.error("HealthMonitor callback error: {}", cb_err)

        return health

    async def check_all(self) -> dict[str, ProviderHealth]:
        """Perform concurrent health checks across all registered providers."""
        provider_ids = self._registry.list_provider_ids()
        tasks = [self.check_provider(pid) for pid in provider_ids]
        await asyncio.gather(*tasks, return_exceptions=True)
        return dict(self._health_map)

    def get_health(self, provider_id: str) -> ProviderHealth | None:
        """Retrieve latest cached health snapshot for a provider."""
        return self._health_map.get(provider_id)

    def is_healthy(self, provider_id: str) -> bool:
        """Check if a provider is currently marked healthy in cache."""
        health = self.get_health(provider_id)
        return health.healthy if health is not None else False

    async def start(self) -> None:
        """Start the background health check monitoring loop."""
        if self._running:
            return
        self._running = True
        logger.info("Started HealthMonitor service (interval={}s)", self._interval_seconds)
        self._task = asyncio.create_task(self._monitor_loop())

    async def stop(self) -> None:
        """Stop the background health check monitoring loop."""
        if not self._running:
            return
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("Stopped HealthMonitor service")

    async def _monitor_loop(self) -> None:
        while self._running:
            try:
                await self.check_all()
            except Exception as err:
                logger.error("Error in HealthMonitor loop: {}", err)
            await asyncio.sleep(self._interval_seconds)
