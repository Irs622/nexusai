"""Model Context Protocol (MCP) Subsystem for NexusAI.

Provides MCP clients (stdio & SSE/HTTP streaming), dynamic tool wrapping, and multi-server lifecycle management.
"""

from nexusai.tools.mcp.base import BaseMcpClient, SseEvent
from nexusai.tools.mcp.client import McpClient
from nexusai.tools.mcp.manager import McpServerManager
from nexusai.tools.mcp.models import (
    JsonRpcError,
    JsonRpcRequest,
    JsonRpcResponse,
    McpCallToolResult,
    McpClientInfo,
    McpPromptArgument,
    McpPromptDefinition,
    McpResourceDefinition,
    McpServerConfig,
    McpServerInfo,
    McpToolContent,
    McpToolDefinition,
    McpTransportType,
)
from nexusai.tools.mcp.sse_client import McpSseClient
from nexusai.tools.mcp.tool import McpToolWrapper
from nexusai.tools.mcp.transport import McpHttpTransport

__all__ = [
    "BaseMcpClient",
    "JsonRpcError",
    "JsonRpcRequest",
    "JsonRpcResponse",
    "McpCallToolResult",
    "McpClient",
    "McpClientInfo",
    "McpHttpTransport",
    "McpPromptArgument",
    "McpPromptDefinition",
    "McpResourceDefinition",
    "McpServerConfig",
    "McpServerInfo",
    "McpServerManager",
    "McpSseClient",
    "McpToolContent",
    "McpToolDefinition",
    "McpToolWrapper",
    "McpTransportType",
    "SseEvent",
]
