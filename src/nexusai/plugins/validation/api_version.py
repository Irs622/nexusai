"""
API Version Negotiator for multi-version kernel/plugin compatibility matrix.
"""

from __future__ import annotations

from nexusai.plugins.contracts.manifest import PluginManifest
from nexusai.plugins.exceptions import PluginAPIVersionError


class APIVersionNegotiator:
    """Evaluates kernel-to-plugin API compatibility rules and compatibility matrix."""

    CURRENT_KERNEL_VERSION = "0.2.0"
    CURRENT_KERNEL_API = 1
    CURRENT_PLUGIN_API = 1

    COMPATIBILITY_MATRIX: dict[int, list[int]] = {
        # Kernel API Major Version : List of supported Plugin API Major Versions
        1: [1],
        2: [1, 2],
    }

    def evaluate_compatibility(self, manifest: PluginManifest) -> bool:
        """Verify plugin compatibility against kernel rules.

        Raises:
            PluginAPIVersionError: If compatibility check fails.
        """
        # 1. Check Kernel API Major compatibility
        supported_plugin_apis = self.COMPATIBILITY_MATRIX.get(
            self.CURRENT_KERNEL_API, [self.CURRENT_PLUGIN_API]
        )
        if manifest.plugin_api not in supported_plugin_apis:
            raise PluginAPIVersionError(
                f"Plugin '{manifest.id}' requires Plugin API v{manifest.plugin_api}, "
                f"but Kernel API v{self.CURRENT_KERNEL_API} supports APIs: {supported_plugin_apis}"
            )

        # 2. Check minimum kernel version rule
        if self._parse_version(manifest.minimum_kernel) > self._parse_version(
            self.CURRENT_KERNEL_VERSION
        ):
            raise PluginAPIVersionError(
                f"Plugin '{manifest.id}' requires minimum kernel version v{manifest.minimum_kernel}, "
                f"but current kernel version is v{self.CURRENT_KERNEL_VERSION}"
            )

        return True

    @staticmethod
    def _parse_version(version_str: str) -> tuple[int, ...]:
        """Convert semver string into comparable integer tuple."""
        clean_str = version_str.split("-")[0]
        try:
            return tuple(int(x) for x in clean_str.split("."))
        except Exception:
            return (0, 0, 0)
