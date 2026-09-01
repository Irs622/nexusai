"""Model Context Protocol (MCP) Subsystem for NexusAI.

Provides MCP client, dynamic tool wrapping, and multi-server lifecycle management.
"""

from nexusai.tools.mcp.client import McpClient
from nexusai.tools.mcp.manager import McpServerManager
from nexusai.tools.mcp.models import (
    JsonRpcError,
    JsonRpcRequest,
    JsonRpcResponse,
    McpCallToolResult,
    McpClientInfo,
    McpServerConfig,
    McpServerInfo,
    McpToolContent,
    McpToolDefinition,
)
from nexusai.tools.mcp.tool import McpToolWrapper

__all__ = [
    "JsonRpcError",
    "JsonRpcRequest",
    "JsonRpcResponse",
    "McpCallToolResult",
    "McpClient",
    "McpClientInfo",
    "McpServerConfig",
    "McpServerInfo",
    "McpServerManager",
    "McpToolContent",
    "McpToolDefinition",
    "McpToolWrapper",
]
