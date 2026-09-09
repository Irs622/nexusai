"""Abstract base interfaces and common data structures for Model Context Protocol (MCP) clients."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from nexusai.tools.mcp.models import (
    McpCallToolResult,
    McpPromptDefinition,
    McpResourceDefinition,
    McpToolDefinition,
)


@dataclass(frozen=True)
class SseEvent:
    """Represents a discrete Server-Sent Event frame conforming to the W3C EventSource standard."""

    event: str = "message"
    data: str = ""
    id: str | None = None
    retry: int | None = None


class BaseMcpClient(ABC):
    """Abstract base class for MCP clients managing standard I/O or remote streaming transports."""

    @property
    @abstractmethod
    def is_connected(self) -> bool:
        """Return True if connection or subprocess is active and initialized."""
        ...

    @property
    @abstractmethod
    def server_name(self) -> str:
        """Return identifier name for this server."""
        ...

    async def __aenter__(self) -> BaseMcpClient:
        await self.start()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.stop()

    @abstractmethod
    async def start(self) -> None:
        """Initialize transport, connect to server, and execute protocol handshake."""
        ...

    @abstractmethod
    async def stop(self) -> None:
        """Gracefully terminate transport and tear down active streams/processes."""
        ...

    @abstractmethod
    async def list_tools(self) -> list[McpToolDefinition]:
        """Fetch list of available tools declared by this MCP server."""
        ...

    @abstractmethod
    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> McpCallToolResult:
        """Execute a tool on the MCP server and return structured result."""
        ...

    @abstractmethod
    async def ping(self) -> bool:
        """Send ping request to check server responsiveness."""
        ...

    @abstractmethod
    async def list_prompts(self) -> list[McpPromptDefinition]:
        """Fetch list of available prompt templates declared by this MCP server."""
        ...

    @abstractmethod
    async def list_resources(self) -> list[McpResourceDefinition]:
        """Fetch list of available data resources declared by this MCP server."""
        ...
