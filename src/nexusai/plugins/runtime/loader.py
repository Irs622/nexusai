"""
Single-responsibility PluginLoader for fault-isolated module loading.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Type

from nexusai.plugins.contracts.base import BasePlugin
from nexusai.plugins.contracts.context import PluginContext
from nexusai.plugins.contracts.manifest import PluginManifest
from nexusai.plugins.exceptions import PluginLoadError


class PluginLoader:
    """Imports entrypoint modules and instantiates BasePlugin implementations."""

    def load_plugin_instance(
        self,
        manifest: PluginManifest,
        context: PluginContext,
        plugin_location: Path | None = None,
    ) -> BasePlugin:
        """Dynamically import module, instantiate plugin class, and inject context.

        Raises:
            PluginLoadError: If importing or instantiation fails.
        """
        # Ensure plugin location is in sys.path if directory
        if plugin_location and plugin_location.exists():
            loc_str = str(plugin_location.resolve())
            if loc_str not in sys.path:
                sys.path.insert(0, loc_str)

        entrypoint = manifest.entrypoint
        if ":" not in entrypoint:
            raise PluginLoadError(f"Invalid entrypoint '{entrypoint}' in manifest '{manifest.id}'")

        module_path, class_name = entrypoint.split(":", 1)

        try:
            module = importlib.import_module(module_path)
        except Exception as e:
            raise PluginLoadError(
                f"Failed to import plugin module '{module_path}' for plugin '{manifest.id}': {e}"
            ) from e

        if not hasattr(module, class_name):
            raise PluginLoadError(
                f"Plugin class '{class_name}' not found in module '{module_path}' for plugin '{manifest.id}'"
            )

        plugin_cls: Type[BasePlugin] = getattr(module, class_name)
        if not issubclass(plugin_cls, BasePlugin):
            raise PluginLoadError(
                f"Class '{class_name}' in '{module_path}' does not inherit from BasePlugin"
            )

        try:
            instance = plugin_cls(manifest=manifest, context=context)
            return instance
        except Exception as e:
            raise PluginLoadError(
                f"Failed to instantiate plugin class '{class_name}' for plugin '{manifest.id}': {e}"
            ) from e
