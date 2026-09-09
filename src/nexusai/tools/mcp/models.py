"""Pydantic schemas and dataclasses for Model Context Protocol (MCP) and JSON-RPC 2.0."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from nexusai.security.guard import RiskLevel


class McpTransportType(str, Enum):
    """Supported transport mechanisms for Model Context Protocol connections."""

    STDIO = "stdio"
    SSE = "sse"
    HTTP = "http"


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


class McpPromptArgument(BaseModel):
    """Argument specification for an MCP Prompt."""

    name: str
    description: str = ""
    required: bool = False


class McpPromptDefinition(BaseModel):
    """Specification of an MCP Prompt template advertised by an MCP server."""

    name: str
    description: str = ""
    arguments: list[McpPromptArgument] = Field(default_factory=list)


class McpResourceDefinition(BaseModel):
    """Specification of an MCP Resource advertised by an MCP server."""

    uri: str
    name: str = ""
    description: str = ""
    mime_type: str | None = Field(default=None, alias="mimeType")

    model_config = ConfigDict(populate_by_name=True)


class McpServerConfig(BaseModel):
    """Configuration model for an individual MCP server connection."""

    name: str
    transport: McpTransportType = McpTransportType.STDIO
    command: str | None = None
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    url: str | None = None
    headers: dict[str, str] = Field(default_factory=dict)
    enabled: bool = True
    risk_level: RiskLevel = RiskLevel.MEDIUM
    timeout_seconds: float = 30.0
    reconnect_retries: int = 3
    reconnect_backoff_seconds: float = 1.0
    reconnect_max_backoff_seconds: float = 30.0
    heartbeat_interval_seconds: float = 30.0

    @model_validator(mode="before")
    @classmethod
    def validate_transport_and_targets(cls, data: Any) -> Any:
        """Validate that transport and required target fields (command vs url) are consistent."""
        if not isinstance(data, dict):
            return data

        transport = data.get("transport")
        url = data.get("url")
        command = data.get("command")

        # Auto-infer transport if omitted
        if transport is None:
            if url and not command:
                data["transport"] = McpTransportType.SSE
                transport = McpTransportType.SSE
            else:
                data["transport"] = McpTransportType.STDIO
                transport = McpTransportType.STDIO
        elif isinstance(transport, str):
            try:
                transport = McpTransportType(transport.lower())
                data["transport"] = transport
            except ValueError:
                raise ValueError(
                    f"Unsupported MCP transport '{transport}'. Must be one of {[t.value for t in McpTransportType]}"
                )

        if transport == McpTransportType.STDIO and not command:
            raise ValueError("Field 'command' is required when transport is 'stdio'")

        if transport in (McpTransportType.SSE, McpTransportType.HTTP) and not url:
            raise ValueError(f"Field 'url' is required when transport is '{transport.value}'")

        return data


class McpClientInfo(BaseModel):
    """Client metadata sent during MCP initialization."""

    name: str = "NexusAI"
    version: str = "1.0.0"


class McpServerInfo(BaseModel):
    """Server metadata received during MCP initialization."""

    name: str
    version: str = "1.0.0"
