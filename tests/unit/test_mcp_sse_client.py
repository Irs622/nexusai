"""Unit tests for McpHttpTransport, McpSseClient, and remote MCP streaming communication."""

from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from nexusai.core.errors import ToolExecutionError
from nexusai.security.guard import RiskLevel
from nexusai.tools.mcp.base import SseEvent
from nexusai.tools.mcp.models import (
    McpCallToolResult,
    McpServerConfig,
    McpTransportType,
)
from nexusai.tools.mcp.sse_client import McpSseClient
from nexusai.tools.mcp.transport import McpHttpTransport


class MockAsyncLineIterator:
    """Mock asynchronous line iterator for httpx.Response.aiter_lines()."""

    def __init__(self, lines: list[str]) -> None:
        self.lines = lines
        self.idx = 0

    def __aiter__(self) -> MockAsyncLineIterator:
        return self

    async def __anext__(self) -> str:
        if self.idx < len(self.lines):
            line = self.lines[self.idx]
            self.idx += 1
            await asyncio.sleep(0.005)
            return line
        # Keep waiting or exit
        await asyncio.sleep(0.02)
        raise StopAsyncIteration


@pytest.mark.asyncio
async def test_sse_event_parsing() -> None:
    """Verify W3C EventSource compliant line and frame parsing in McpHttpTransport."""
    transport = McpHttpTransport()

    raw_stream = [
        ": keepalive comment",
        "event: endpoint",
        "data: /messages?sessionId=abc",
        "",
        ": another comment",
        "event: message",
        "id: 101",
        "retry: 5000",
        'data: {"jsonrpc": "2.0",',
        'data: "id": 1,',
        'data: "result": {"status": "ok"}}',
        "",
    ]

    mock_resp = AsyncMock()
    mock_resp.status_code = 200
    mock_resp.aiter_lines = lambda: MockAsyncLineIterator(raw_stream)

    mock_stream_ctx = AsyncMock()
    mock_stream_ctx.__aenter__.return_value = mock_resp
    mock_stream_ctx.__aexit__.return_value = None

    with patch.object(transport.client, "stream", return_value=mock_stream_ctx):
        events: list[SseEvent] = []
        async for event in transport.stream_sse("http://localhost:8000/sse"):
            events.append(event)

        assert len(events) == 2

        # 1. Endpoint event
        assert events[0].event == "endpoint"
        assert events[0].data == "/messages?sessionId=abc"

        # 2. Multiline JSON-RPC message event
        assert events[1].event == "message"
        assert events[1].id == "101"
        assert events[1].retry == 5000
        parsed_data = json.loads(events[1].data)
        assert parsed_data["id"] == 1
        assert parsed_data["result"] == {"status": "ok"}

    await transport.close()


@pytest.fixture
def sample_sse_config() -> McpServerConfig:
    return McpServerConfig(
        name="remote_mock",
        transport=McpTransportType.SSE,
        url="http://localhost:9090/sse",
        headers={"Authorization": "Bearer secret_token"},
        timeout_seconds=2.0,
        risk_level=RiskLevel.LOW,
        reconnect_retries=2,
        reconnect_backoff_seconds=0.05,
        heartbeat_interval_seconds=0.0,  # Disabled in unit tests for speed
    )


@pytest.mark.asyncio
async def test_mcp_sse_client_lifecycle_and_tool_call(sample_sse_config: McpServerConfig) -> None:
    """Test full MCP SSE client lifecycle: endpoint discovery, handshake, tools/list, and tools/call."""
    client = McpSseClient(sample_sse_config)

    # Simulated SSE stream events
    sse_lines = [
        "event: endpoint",
        "data: /messages?sessionId=xyz-123",
        "",
        # Initialize response
        "event: message",
        'data: {"jsonrpc": "2.0", "id": 1, "result": {"protocolVersion": "2024-11-05", "serverInfo": {"name": "RemoteMock", "version": "1.0.0"}}}',
        "",
        # tools/list response
        "event: message",
        'data: {"jsonrpc": "2.0", "id": 2, "result": {"tools": [{"name": "remote_echo", "description": "Echo input", "inputSchema": {"type": "object"}}]}}',
        "",
        # tools/call response (1)
        "event: message",
        'data: {"jsonrpc": "2.0", "id": 3, "result": {"content": [{"type": "text", "text": "Echo: Hello Remote MCP!"}], "isError": false}}',
        "",
        # tools/call response (2 for stream_tool_call)
        "event: message",
        'data: {"jsonrpc": "2.0", "id": 4, "result": {"content": [{"type": "text", "text": "Chunk 1"}, {"type": "text", "text": "Chunk 2"}], "isError": false}}',
        "",
        # ping response
        "event: message",
        'data: {"jsonrpc": "2.0", "id": 5, "result": {}}',
        "",
    ]

    mock_resp = AsyncMock()
    mock_resp.status_code = 200
    mock_resp.aiter_lines = lambda: MockAsyncLineIterator(sse_lines)

    mock_stream_ctx = AsyncMock()
    mock_stream_ctx.__aenter__.return_value = mock_resp
    mock_stream_ctx.__aexit__.return_value = None

    posted_payloads: list[dict[str, Any]] = []

    async def fake_post_json(
        url: str, payload: dict[str, Any], headers: Any = None
    ) -> tuple[int, Any, str]:
        posted_payloads.append(payload)
        # Return 202 Accepted without direct body (response delivered over SSE stream)
        return 202, None, "Accepted"

    with patch(
        "nexusai.tools.mcp.transport.httpx.AsyncClient.stream", return_value=mock_stream_ctx
    ):
        with patch.object(McpHttpTransport, "post_json", side_effect=fake_post_json):
            await client.start()
            assert client.is_connected is True
            assert client.server_name == "remote_mock"
            assert client.post_url == "http://localhost:9090/messages?sessionId=xyz-123"

            # 1. Verify Handshake POSTs
            assert len(posted_payloads) >= 2
            assert posted_payloads[0]["method"] == "initialize"
            assert posted_payloads[1]["method"] == "notifications/initialized"

            # 2. List tools
            tools = await client.list_tools()
            assert len(tools) == 1
            assert tools[0].name == "remote_echo"
            assert tools[0].description == "Echo input"

            # 3. Call tool
            call_res: McpCallToolResult = await client.call_tool("remote_echo", {"msg": "Hello"})
            assert call_res.is_error is False
            assert call_res.extract_text() == "Echo: Hello Remote MCP!"

            # 4. Stream tool call chunks
            chunks = [
                chunk async for chunk in client.stream_tool_call("remote_echo", {"msg": "Hello"})
            ]
            assert len(chunks) == 2
            assert chunks[0].text == "Chunk 1"
            assert chunks[1].text == "Chunk 2"

            # 5. Ping
            alive = await client.ping()
            assert alive is True

            await client.stop()
            assert client.is_connected is False


@pytest.mark.asyncio
async def test_mcp_sse_client_direct_http_response(sample_sse_config: McpServerConfig) -> None:
    """Test client when remote server returns JSON-RPC responses directly in HTTP POST response body."""
    client = McpSseClient(sample_sse_config)

    sse_lines = [
        "event: endpoint",
        "data: /rpc",
        "",
    ]

    mock_resp = AsyncMock()
    mock_resp.status_code = 200
    mock_resp.aiter_lines = lambda: MockAsyncLineIterator(sse_lines)

    mock_stream_ctx = AsyncMock()
    mock_stream_ctx.__aenter__.return_value = mock_resp
    mock_stream_ctx.__aexit__.return_value = None

    async def fake_post_json(
        url: str, payload: dict[str, Any], headers: Any = None
    ) -> tuple[int, Any, str]:
        req_id = payload.get("id")
        method = payload.get("method")
        if method == "initialize":
            return (
                200,
                {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {"serverInfo": {"name": "DirectServer"}},
                },
                "",
            )
        if method == "tools/list":
            return (
                200,
                {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {"tools": [{"name": "direct_tool", "description": "Direct Tool"}]},
                },
                "",
            )
        if method == "tools/call":
            return (
                200,
                {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": "Direct Execution Success"}],
                        "isError": False,
                    },
                },
                "",
            )
        return 200, {"jsonrpc": "2.0", "id": req_id, "result": {}}, ""

    with patch(
        "nexusai.tools.mcp.transport.httpx.AsyncClient.stream", return_value=mock_stream_ctx
    ):
        with patch.object(McpHttpTransport, "post_json", side_effect=fake_post_json):
            await client.start()
            assert client.is_connected is True

            tools = await client.list_tools()
            assert len(tools) == 1
            assert tools[0].name == "direct_tool"

            result = await client.call_tool("direct_tool", {})
            assert result.extract_text() == "Direct Execution Success"

            await client.stop()


@pytest.mark.asyncio
async def test_mcp_sse_client_prompts_and_resources(sample_sse_config: McpServerConfig) -> None:
    """Verify discovery of prompts and resources from remote MCP server."""
    client = McpSseClient(sample_sse_config)

    sse_lines = [
        "event: endpoint",
        "data: /rpc",
        "",
    ]

    mock_resp = AsyncMock()
    mock_resp.status_code = 200
    mock_resp.aiter_lines = lambda: MockAsyncLineIterator(sse_lines)
    mock_stream_ctx = AsyncMock()
    mock_stream_ctx.__aenter__.return_value = mock_resp
    mock_stream_ctx.__aexit__.return_value = None

    async def fake_post_json(
        url: str, payload: dict[str, Any], headers: Any = None
    ) -> tuple[int, Any, str]:
        req_id = payload.get("id")
        method = payload.get("method")
        if method == "initialize":
            return 200, {"jsonrpc": "2.0", "id": req_id, "result": {}}, ""
        if method == "prompts/list":
            return (
                200,
                {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "prompts": [
                            {
                                "name": "summarize_doc",
                                "description": "Summarize a document",
                                "arguments": [{"name": "text", "required": True}],
                            }
                        ]
                    },
                },
                "",
            )
        if method == "resources/list":
            return (
                200,
                {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "resources": [
                            {
                                "uri": "postgres://db/schema",
                                "name": "Database Schema",
                                "mimeType": "application/json",
                            }
                        ]
                    },
                },
                "",
            )
        return 200, {"jsonrpc": "2.0", "id": req_id, "result": {}}, ""

    with patch(
        "nexusai.tools.mcp.transport.httpx.AsyncClient.stream", return_value=mock_stream_ctx
    ):
        with patch.object(McpHttpTransport, "post_json", side_effect=fake_post_json):
            await client.start()

            prompts = await client.list_prompts()
            assert len(prompts) == 1
            assert prompts[0].name == "summarize_doc"
            assert len(prompts[0].arguments) == 1
            assert prompts[0].arguments[0].name == "text"

            resources = await client.list_resources()
            assert len(resources) == 1
            assert resources[0].uri == "postgres://db/schema"
            assert resources[0].mime_type == "application/json"

            await client.stop()


@pytest.mark.asyncio
async def test_mcp_sse_client_server_error(sample_sse_config: McpServerConfig) -> None:
    """Verify that JSON-RPC errors and HTTP errors raise ToolExecutionError."""
    client = McpSseClient(sample_sse_config)

    sse_lines = [
        "event: endpoint",
        "data: /rpc",
        "",
        # Initialize response
        "event: message",
        'data: {"jsonrpc": "2.0", "id": 1, "result": {}}',
        "",
        # Tool execution error
        "event: message",
        'data: {"jsonrpc": "2.0", "id": 2, "error": {"code": -32001, "message": "Access denied by policy"}}',
        "",
    ]

    mock_resp = AsyncMock()
    mock_resp.status_code = 200
    mock_resp.aiter_lines = lambda: MockAsyncLineIterator(sse_lines)
    mock_stream_ctx = AsyncMock()
    mock_stream_ctx.__aenter__.return_value = mock_resp
    mock_stream_ctx.__aexit__.return_value = None

    async def fake_post_json(
        url: str, payload: dict[str, Any], headers: Any = None
    ) -> tuple[int, Any, str]:
        return 202, None, "Accepted"

    with patch(
        "nexusai.tools.mcp.transport.httpx.AsyncClient.stream", return_value=mock_stream_ctx
    ):
        with patch.object(McpHttpTransport, "post_json", side_effect=fake_post_json):
            await client.start()

            with pytest.raises(ToolExecutionError) as exc_info:
                await client.call_tool("restricted_tool", {})
            assert "Access denied by policy" in str(exc_info.value)

            await client.stop()


def test_mcp_server_config_validation() -> None:
    """Verify McpServerConfig transport auto-inference and target validation."""
    # 1. Stdio config validation
    cfg_stdio = McpServerConfig(name="local_fs", command="python3", args=["-m", "fs"])
    assert cfg_stdio.transport == McpTransportType.STDIO
    assert cfg_stdio.command == "python3"

    # Missing command on stdio raises ValueError
    with pytest.raises(ValueError, match="Field 'command' is required"):
        McpServerConfig(name="bad_stdio", transport=McpTransportType.STDIO)

    # 2. SSE config validation
    cfg_sse = McpServerConfig(name="remote_sse", url="http://localhost:8080/sse")
    assert cfg_sse.transport == McpTransportType.SSE
    assert cfg_sse.url == "http://localhost:8080/sse"

    # Missing url on SSE raises ValueError
    with pytest.raises(ValueError, match="Field 'url' is required"):
        McpServerConfig(name="bad_sse", transport=McpTransportType.SSE)


@pytest.mark.asyncio
async def test_mcp_sse_client_reconnect_recovery() -> None:
    """Verify automatic reconnection with exponential backoff when connection drops."""
    config = McpServerConfig(
        name="reconnect_test",
        transport=McpTransportType.SSE,
        url="http://localhost:9090/sse",
        timeout_seconds=2.0,
        reconnect_retries=2,
        reconnect_backoff_seconds=0.01,
        reconnect_max_backoff_seconds=0.05,
        heartbeat_interval_seconds=0.05,
    )
    client = McpSseClient(config)

    # Stream lines that finish immediately to simulate connection dropping
    sse_lines = [
        "event: endpoint",
        "data: /rpc",
        "",
        "event: message",
        'data: {"jsonrpc": "2.0", "id": 1, "result": {}}',
        "",
    ]

    mock_resp = AsyncMock()
    mock_resp.status_code = 200
    mock_resp.aiter_lines = lambda: MockAsyncLineIterator(sse_lines)
    mock_stream_ctx = AsyncMock()
    mock_stream_ctx.__aenter__.return_value = mock_resp
    mock_stream_ctx.__aexit__.return_value = None

    async def fake_post_json(
        url: str, payload: dict[str, Any], headers: Any = None
    ) -> tuple[int, Any, str]:
        req_id = payload.get("id")
        return 200, {"jsonrpc": "2.0", "id": req_id, "result": {}}, ""

    with patch(
        "nexusai.tools.mcp.transport.httpx.AsyncClient.stream", return_value=mock_stream_ctx
    ):
        with patch.object(McpHttpTransport, "post_json", side_effect=fake_post_json):
            await client.start()
            assert client.is_connected is True

            # Trigger artificial stream drop
            client._is_connected = False
            # Trigger reconnect
            await client._trigger_reconnect()
            assert client.is_connected is True

            await client.stop()
