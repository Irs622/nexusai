"""
BasePlugin abstract contract for all NexusAI plugins.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from nexusai.plugins.contracts.context import PluginContext
from nexusai.plugins.contracts.manifest import PluginManifest


class BasePlugin(ABC):
    """Abstract base class for all NexusAI OS plugins."""

    def __init__(self, manifest: PluginManifest, context: PluginContext) -> None:
        self._manifest = manifest
        self._context = context

    @property
    def manifest(self) -> PluginManifest:
        """Return the plugin manifest."""
        return self._manifest

    @property
    def context(self) -> PluginContext:
        """Return the injected plugin context."""
        return self._context

    @property
    def plugin_id(self) -> str:
        """Return unique plugin ID."""
        return self._manifest.id

    async def on_load(self) -> None:
        """Lifecycle hook executed immediately after module load."""
        pass

    async def on_initialize(self) -> None:
        """Lifecycle hook executed after context injection."""
        pass

    @abstractmethod
    async def on_start(self) -> None:
        """Lifecycle hook executed when starting plugin services."""
        pass

    async def on_stop(self) -> None:
        """Lifecycle hook executed when stopping plugin services."""
        pass

    async def on_unload(self) -> None:
        """Lifecycle hook executed prior to unloading plugin from memory."""
        pass
