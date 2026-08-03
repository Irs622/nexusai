"""Dynamic AI Tool Selector & Ranking Engine."""
from typing import List, Dict, Any
from nexusai.tools.registry import ToolRegistry
from nexusai.tools.base import BaseTool

class ToolSelector:
    """Evaluates task descriptions and dynamically ranks the most relevant tools."""

    def __init__(self, registry: ToolRegistry) -> None:
        self.registry = registry

    def select_best_tool(self, task_description: str) -> BaseTool:
        """Select highest-ranked tool for a given task description."""
        desc_lower = task_description.lower()
        tools = self.registry.get_all_tools()

        for tool in tools:
            if "read" in desc_lower or "file" in desc_lower:
                if tool.name == "workspace_read_file":
                    return tool
            if "list" in desc_lower or "directory" in desc_lower or "folder" in desc_lower:
                if tool.name == "workspace_list_directory":
                    return tool
            if "terminal" in desc_lower or "command" in desc_lower or "shell" in desc_lower or "exec" in desc_lower:
                if tool.name == "execute_terminal":
                    return tool

        # Default fallback to first available tool
        return tools[0] if tools else None
