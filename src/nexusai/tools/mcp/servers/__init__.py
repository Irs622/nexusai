"""Built-in Model Context Protocol (MCP) Server Pack for NexusAI."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nexusai.tools.mcp.servers.base import McpServerBase
    from nexusai.tools.mcp.servers.filesystem import FilesystemMcpServer
    from nexusai.tools.mcp.servers.sqlite import SqliteMcpServer
    from nexusai.tools.mcp.servers.web_fetcher import WebFetcherMcpServer


def __getattr__(name: str) -> object:
    """Lazy-load server classes to prevent runpy submodule pre-import warnings."""
    if name == "McpServerBase":
        from nexusai.tools.mcp.servers.base import McpServerBase

        return McpServerBase
    elif name == "FilesystemMcpServer":
        from nexusai.tools.mcp.servers.filesystem import FilesystemMcpServer

        return FilesystemMcpServer
    elif name == "SqliteMcpServer":
        from nexusai.tools.mcp.servers.sqlite import SqliteMcpServer

        return SqliteMcpServer
    elif name == "WebFetcherMcpServer":
        from nexusai.tools.mcp.servers.web_fetcher import WebFetcherMcpServer

        return WebFetcherMcpServer
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "FilesystemMcpServer",
    "McpServerBase",
    "SqliteMcpServer",
    "WebFetcherMcpServer",
]
