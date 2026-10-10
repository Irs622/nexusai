"""
Canonical PluginLoader for NexusAI.

One class covers both plugin-loading paths:

* ``load_plugin_instance`` imports a manifest entrypoint and instantiates a
  :class:`BasePlugin` with its :class:`PluginContext` (plugin runtime lifecycle).
* ``load_from_module_path`` discovers tool plugins in a module and registers their
  tools into a :class:`ToolRegistry`, enforcing the trust list and manifest
  capability policy *before* the module is imported.

``nexusai.tools.plugin_loader`` is a deprecated alias of this module.
"""

from __future__ import annotations

import importlib
import inspect
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, Type

import yaml

from nexusai.plugins.contracts.base import BasePlugin
from nexusai.plugins.contracts.context import PluginContext
from nexusai.plugins.contracts.manifest import PluginManifest
from nexusai.plugins.exceptions import PluginLoadError

if TYPE_CHECKING:
    from nexusai.security.policy import PluginPolicyEngine
    from nexusai.tools.base import BaseTool
    from nexusai.tools.plugin_manifest import PluginManifest as ToolPluginManifest
    from nexusai.tools.registry import ToolRegistry

__all__ = ["PluginLoader", "PluginLoadError"]


class PluginLoader:
    """Imports plugin modules, instantiates plugins, and registers discovered tools."""

    DEFAULT_TRUSTED_PREFIXES = ("plugins.calculator", "plugins.git", "plugins.filesystem")

    def __init__(
        self,
        registry: ToolRegistry | None = None,
        policy_engine: PluginPolicyEngine | None = None,
        trusted_modules: set[str] | list[str] | None = None,
    ) -> None:
        """Create a loader.

        Args:
            registry: Tool registry that receives tools from ``load_from_module_path``.
                Not needed for ``load_plugin_instance``.
            policy_engine: Capability policy applied to tool-plugin manifests before
                import. Defaults to an engine with default capabilities.
            trusted_modules: Extra module paths (and their sub-modules) that may be
                imported without a manifest.
        """
        self.registry = registry
        self._policy_engine = policy_engine
        self.trusted_modules = set(trusted_modules) if trusted_modules is not None else set()

    @property
    def policy_engine(self) -> PluginPolicyEngine:
        """Capability policy engine, created lazily with default capabilities."""
        if self._policy_engine is None:
            from nexusai.security.policy import PluginPolicyEngine
            from nexusai.tools.plugin_manifest import PluginCapabilities

            self._policy_engine = PluginPolicyEngine(PluginCapabilities())
        return self._policy_engine

    # ------------------------------------------------------------------
    # Plugin runtime path (BasePlugin + PluginContext)
    # ------------------------------------------------------------------
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

    # ------------------------------------------------------------------
    # Tool plugin path (ToolRegistry + pre-import policy enforcement)
    # ------------------------------------------------------------------
    def _locate_manifest(self, module_path: str) -> ToolPluginManifest | None:
        """Attempt to discover and parse a plugin manifest from the filesystem before module import."""
        from nexusai.tools.plugin_manifest import PluginManifest as ToolPluginManifest

        parts = module_path.split(".")
        potential_dirs: list[Path] = []
        if len(parts) > 1:
            potential_dirs.append(Path(*parts[:-1]))
        potential_dirs.append(Path(*parts))

        for base_dir in potential_dirs:
            for manifest_name in ("nexusai_manifest.yaml", "manifest.yaml", "manifest.json"):
                manifest_path = base_dir / manifest_name
                if manifest_path.is_file():
                    try:
                        content = manifest_path.read_text(encoding="utf-8")
                        if manifest_name.endswith(".json"):
                            data = json.loads(content)
                        else:
                            data = yaml.safe_load(content)
                        return ToolPluginManifest(**data)
                    except Exception as e:
                        raise PluginLoadError(
                            f"Invalid plugin manifest at '{manifest_path}': {e}"
                        ) from e
        return None

    def load_from_module_path(
        self, module_path: str, manifest: ToolPluginManifest | None = None
    ) -> list[BaseTool]:
        """Dynamically load tools from a given python module dot path after policy verification.

        Pre-import Verification:
        1. Verify plugin module is either in approved trust list or possesses a valid manifest.
        2. Validate declared manifest capabilities against PluginPolicyEngine BEFORE importlib.import_module().

        Raises:
            PluginLoadError: If no registry is configured, the module is untrusted, or
                importing/instantiating the plugin fails.
        """
        from nexusai.tools.base import BaseTool

        if self.registry is None:
            raise PluginLoadError("load_from_module_path requires a ToolRegistry")

        is_trusted = (
            module_path in self.trusted_modules
            or any(
                module_path == p or module_path.startswith(p + ".")
                for p in self.DEFAULT_TRUSTED_PREFIXES
            )
            or any(
                module_path == m or module_path.startswith(m + ".") for m in self.trusted_modules
            )
        )

        effective_manifest = manifest or self._locate_manifest(module_path)

        if not is_trusted and effective_manifest is None:
            raise PluginLoadError(
                f"Untrusted plugin module '{module_path}': Module is not in approved trust list and has no validated manifest."
            )

        if effective_manifest is not None:
            self.policy_engine.validate_capabilities(effective_manifest)

        try:
            module = importlib.import_module(module_path)
        except Exception as e:
            raise PluginLoadError(f"Failed to import plugin module '{module_path}': {e}") from e

        discovered_tools: list[BaseTool] = []

        for _, obj in inspect.getmembers(module):
            if inspect.isclass(obj) and hasattr(obj, "get_tools") and not inspect.isabstract(obj):
                try:
                    plugin_instance: Any = obj()
                    tools = plugin_instance.get_tools()
                    for t in tools:
                        if isinstance(t, BaseTool):
                            self.registry.register(t)
                            discovered_tools.append(t)
                except Exception as pe:
                    raise PluginLoadError(
                        f"Error instantiating plugin class '{obj.__name__}': {pe}"
                    ) from pe

        return discovered_tools
