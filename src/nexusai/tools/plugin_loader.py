"""Dynamic Plugin Loader & Discovery Subsystem for NexusAI."""
import importlib
import inspect
from typing import List, Type, Any
from nexusai.tools.base import BaseTool
from nexusai.tools.registry import ToolRegistry
from nexusai.core.errors import NexusAIError

class PluginLoadError(NexusAIError):
    """Raised when a plugin fails to load or register."""
    pass

class PluginLoader:
    """Discovers and registers tool plugins dynamically into ToolRegistry."""

    def __init__(self, registry: ToolRegistry) -> None:
        self.registry = registry

    def load_from_module_path(self, module_path: str) -> List[BaseTool]:
        """Dynamically load tools from a given python module dot path."""
        try:
            module = importlib.import_module(module_path)
        except Exception as e:
            raise PluginLoadError(f"Failed to import plugin module '{module_path}': {e}") from e

        discovered_tools: List[BaseTool] = []

        # Check for explicit plugin class with get_tools method
        for _, obj in inspect.getmembers(module):
            if inspect.isclass(obj) and hasattr(obj, "get_tools") and not inspect.isabstract(obj):
                try:
                    plugin_instance = obj()
                    tools = plugin_instance.get_tools()
                    for t in tools:
                        if isinstance(t, BaseTool):
                            self.registry.register(t)
                            discovered_tools.append(t)
                except Exception as pe:
                    raise PluginLoadError(f"Error instantiating plugin class '{obj.__name__}': {pe}") from pe

        return discovered_tools
