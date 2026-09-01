"""Pydantic schemas and dataclasses for Model Context Protocol (MCP) and JSON-RPC 2.0."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from nexusai.security.guard import RiskLevel


class JsonRpcRequest(BaseModel):
    """JSON-RPC 2.0 Request payload."""

    jsonrpc: str = "2.0"
    id: int | str | None = None
    method: str
    params: dict[str, Any] | None = None


class JsonRpcError(BaseModel):
    """JSON-RPC 2.0 Error payload."""

    code: int
    message: str
    data: Any | None = None


class JsonRpcResponse(BaseModel):
    """JSON-RPC 2.0 Response payload."""

    jsonrpc: str = "2.0"
    id: int | str | None = None
    result: Any | None = None
    error: JsonRpcError | None = None


class McpToolDefinition(BaseModel):
    """Specification of an MCP Tool advertised by an MCP server."""

    name: str
    description: str = ""
    input_schema: dict[str, Any] = Field(default_factory=dict, alias="inputSchema")

    model_config = ConfigDict(populate_by_name=True)


class McpToolContent(BaseModel):
    """Content item returned by an MCP tool invocation."""

    type: str = "text"
    text: str | None = None
    data: str | None = None
    mime_type: str | None = Field(default=None, alias="mimeType")

    model_config = ConfigDict(populate_by_name=True)


class McpCallToolResult(BaseModel):
    """Structured result returned by tools/call execution."""

    content: list[McpToolContent] = Field(default_factory=list)
    is_error: bool = Field(default=False, alias="isError")

    model_config = ConfigDict(populate_by_name=True)

    def extract_text(self) -> str:
        """Extract combined text content from result."""
        parts: list[str] = []
        for item in self.content:
            if item.text:
                parts.append(item.text)
        return "\n".join(parts) if parts else ""


class McpServerConfig(BaseModel):
    """Configuration model for an individual MCP server connection."""

    name: str
    command: str
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    enabled: bool = True
    risk_level: RiskLevel = RiskLevel.MEDIUM
    timeout_seconds: float = 30.0


class McpClientInfo(BaseModel):
    """Client metadata sent during MCP initialization."""

    name: str = "NexusAI"
    version: str = "0.7.0"


class McpServerInfo(BaseModel):
    """Server metadata received during MCP initialization."""

    name: str
    version: str = "1.0.0"
