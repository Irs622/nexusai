"""
Central Tool Registry for registering and retrieving system capabilities.
"""

from typing import Any

from nexusai.core.errors import ToolExecutionError
from nexusai.tools.base import BaseTool


class ToolRegistry:
    """Registry managing available tools and exporting LLM function schemas."""

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        """Register a tool instance."""
        if tool.name in self._tools:
            raise ToolExecutionError(f"Tool '{tool.name}' is already registered.")
        self._tools[tool.name] = tool

    def get(self, name: str) -> BaseTool:
        """Retrieve a tool by name."""
        if name not in self._tools:
            raise ToolExecutionError(f"Tool '{name}' not found in registry.")
        return self._tools[name]

    def has_tool(self, name: str) -> bool:
        """Check if a tool is registered."""
        return name in self._tools

    def get_all_tools(self) -> list[BaseTool]:
        """Return a list of all registered tool instances."""
        return list(self._tools.values())

    def get_all_schemas(self) -> list[dict[str, Any]]:
        """Export all registered tools into LLM function-calling JSON schemas."""
        return [tool.to_json_schema() for tool in self._tools.values()]

    def unregister(self, name: str) -> bool:
        """Unregister a tool by name if present. Returns True if removed, False otherwise."""
        if name in self._tools:
            del self._tools[name]
            return True
        return False

    def clear(self) -> None:
        """Unregister all tools."""
        self._tools.clear()
