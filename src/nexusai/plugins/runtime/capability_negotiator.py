"""
CapabilityNegotiator for constraint-based plugin resolution.
"""

from __future__ import annotations

from typing import Any

from nexusai.plugins.contracts.capability import Capability
from nexusai.plugins.runtime.descriptor import PluginDescriptor
from nexusai.plugins.runtime.registry import PluginRegistry


class CapabilityNegotiator:
    """Matches registered plugin descriptors using capability and constraint rules."""

    def __init__(self, registry: PluginRegistry) -> None:
        self.registry = registry

    def negotiate(
        self,
        capability: Capability | str,
        constraints: dict[str, Any] | None = None,
    ) -> list[PluginDescriptor]:
        """Filter registered plugins by capability and constraint criteria.

        Supported constraints:
            - supports_stream (bool)
            - vision (bool)
            - priority (int)

        Returns:
            Matching plugin descriptors.
        """
        descriptors = self.registry.resolve_capability(capability)
        if not constraints:
            return descriptors

        matching: list[PluginDescriptor] = []
        for desc in descriptors:
            manifest_perms = desc.manifest.permissions
            # Example constraint checks
            match = True
            for key, expected_val in constraints.items():
                actual_val = manifest_perms.get(key)
                if actual_val != expected_val:
                    match = False
                    break
            if match:
                matching.append(desc)

        return matching
