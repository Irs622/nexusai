"""
PluginRegistry for metadata descriptor storage and capability resolution.
"""

from __future__ import annotations

from typing import Sequence

from nexusai.plugins.contracts.capability import Capability
from nexusai.plugins.contracts.state import PluginState
from nexusai.plugins.exceptions import PluginResolutionError
from nexusai.plugins.runtime.descriptor import PluginDescriptor


class PluginRegistry:
    """Centralized registry indexing plugin descriptors and resolving capabilities."""

    def __init__(self) -> None:
        self._descriptors: dict[str, PluginDescriptor] = {}
        self._states: dict[str, PluginState] = {}

    def register(self, descriptor: PluginDescriptor, initial_state: PluginState = PluginState.LOADED) -> None:
        """Register a plugin descriptor in the registry."""
        self._descriptors[descriptor.id] = descriptor
        self._states[descriptor.id] = initial_state

    def unregister(self, plugin_id: str) -> PluginDescriptor | None:
        """Unregister a plugin descriptor."""
        self._states.pop(plugin_id, None)
        return self._descriptors.pop(plugin_id, None)

    def exists(self, plugin_id: str) -> bool:
        """Return True if plugin descriptor exists."""
        return plugin_id in self._descriptors

    def get_descriptor(self, plugin_id: str) -> PluginDescriptor | None:
        """Retrieve plugin descriptor by ID."""
        return self._descriptors.get(plugin_id)

    def get_state(self, plugin_id: str) -> PluginState | None:
        """Retrieve plugin runtime state by ID."""
        return self._states.get(plugin_id)

    def set_state(self, plugin_id: str, state: PluginState) -> None:
        """Update runtime state for registered plugin."""
        if plugin_id in self._descriptors:
            self._states[plugin_id] = state

    def list_plugins(self) -> list[PluginDescriptor]:
        """Return list of all registered plugin descriptors."""
        return list(self._descriptors.values())

    def resolve_capability(self, capability: Capability | str) -> list[PluginDescriptor]:
        """Resolve all registered plugins that provide the given capability."""
        cap_str = str(capability.name if isinstance(capability, Capability) else capability)
        matching: list[PluginDescriptor] = []

        for desc in self._descriptors.values():
            if cap_str in desc.manifest.capabilities:
                matching.append(desc)

        return matching

    def resolve_first(self, capability: Capability | str) -> PluginDescriptor:
        """Resolve the first plugin providing capability or raise PluginResolutionError."""
        matches = self.resolve_capability(capability)
        if not matches:
            cap_str = capability.name if isinstance(capability, Capability) else capability
            raise PluginResolutionError(f"No registered plugin provides capability '{cap_str}'")
        return matches[0]

    def resolve_optional(self, plugin_id: str) -> PluginDescriptor | None:
        """Resolve plugin descriptor by ID if present, otherwise return None."""
        return self.get_descriptor(plugin_id)

    def resolve_required(self, plugin_id: str) -> PluginDescriptor:
        """Resolve plugin descriptor by ID or raise PluginResolutionError."""
        desc = self.get_descriptor(plugin_id)
        if not desc:
            raise PluginResolutionError(f"Required plugin '{plugin_id}' is not registered")
        return desc
