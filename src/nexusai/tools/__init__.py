"""
Tool System Package for NexusAI capabilities.
"""

from typing import Any

__all__ = ["BaseTool", "ToolRegistry", "McpServerManager", "McpToolWrapper"]


def __getattr__(name: str) -> Any:
    if name == "BaseTool":
        from nexusai.tools.base import BaseTool

        return BaseTool
    if name == "ToolRegistry":
        from nexusai.tools.registry import ToolRegistry

        return ToolRegistry
    if name == "McpServerManager":
        from nexusai.tools.mcp.manager import McpServerManager

        return McpServerManager
    if name == "McpToolWrapper":
        from nexusai.tools.mcp.tool import McpToolWrapper

        return McpToolWrapper
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
