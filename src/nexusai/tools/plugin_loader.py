"""Dynamic Plugin Loader & Discovery Subsystem for NexusAI with Pre-Import Security Policy Enforcement."""

from __future__ import annotations

import importlib
import inspect
import json
from pathlib import Path
from typing import Any, List

import yaml

from nexusai.core.errors import NexusAIError
from nexusai.security.policy import PluginPolicyEngine
from nexusai.tools.base import BaseTool
from nexusai.tools.plugin_manifest import PluginCapabilities, PluginManifest
from nexusai.tools.registry import ToolRegistry


class PluginLoadError(NexusAIError):
    """Raised when a plugin fails to load or register."""

    pass


class PluginLoader:
    """Discovers and registers tool plugins dynamically into ToolRegistry with pre-import policy enforcement."""

    DEFAULT_TRUSTED_PREFIXES = ("plugins.calculator", "plugins.git", "plugins.filesystem")

    def __init__(
        self,
        registry: ToolRegistry,
        policy_engine: PluginPolicyEngine | None = None,
        trusted_modules: set[str] | list[str] | None = None,
    ) -> None:
        self.registry = registry
        self.policy_engine = policy_engine or PluginPolicyEngine(PluginCapabilities())
        self.trusted_modules = set(trusted_modules) if trusted_modules is not None else set()

    def _locate_manifest(self, module_path: str) -> PluginManifest | None:
        """Attempt to discover and parse a plugin manifest from the filesystem before module import."""
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
                        return PluginManifest(**data)
                    except Exception as e:
                        raise PluginLoadError(
                            f"Invalid plugin manifest at '{manifest_path}': {e}"
                        ) from e
        return None

    def load_from_module_path(
        self, module_path: str, manifest: PluginManifest | None = None
    ) -> List[BaseTool]:
        """Dynamically load tools from a given python module dot path after policy verification.

        Pre-import Verification:
        1. Verify plugin module is either in approved trust list or possesses a valid manifest.
        2. Validate declared manifest capabilities against PluginPolicyEngine BEFORE importlib.import_module().
        """
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

        # Validate manifest capabilities BEFORE importlib.import_module()
        if effective_manifest is not None:
            self.policy_engine.validate_capabilities(effective_manifest)

        # Import module only after pre-import verification passes
        try:
            module = importlib.import_module(module_path)
        except Exception as e:
            raise PluginLoadError(f"Failed to import plugin module '{module_path}': {e}") from e

        discovered_tools: List[BaseTool] = []

        # Check for explicit plugin class with get_tools method
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
