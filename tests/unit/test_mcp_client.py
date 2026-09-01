"""Unit tests for McpClient and stdio JSON-RPC 2.0 communication."""

from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nexusai.core.errors import ToolExecutionError
from nexusai.security.guard import RiskLevel
from nexusai.tools.mcp.client import McpClient
from nexusai.tools.mcp.models import McpServerConfig


class FakeStreamReader:
    def __init__(self, responses: list[Any]) -> None:
        self._lines = [(json.dumps(r) + "\n").encode("utf-8") for r in responses]
        self._idx = 0

    async def readline(self) -> bytes:
        if self._idx < len(self._lines):
            line = self._lines[self._idx]
            self._idx += 1
            # Add small delay to mimic async I/O
            await asyncio.sleep(0.01)
            return line
        # Keep waiting or return empty (EOF)
        await asyncio.sleep(0.05)
        return b""


class FakeStreamWriter:
    def __init__(self) -> None:
        self.written: list[bytes] = []

    def write(self, data: bytes) -> None:
        self.written.append(data)

    async def drain(self) -> None:
        pass


@pytest.fixture
def sample_config() -> McpServerConfig:
    return McpServerConfig(
        name="test_server",
        command="python3",
        args=["-m", "dummy_server"],
        timeout_seconds=2.0,
        risk_level=RiskLevel.LOW,
    )


@pytest.mark.asyncio
async def test_mcp_client_lifecycle_and_tool_call(sample_config: McpServerConfig) -> None:
    """Test full MCP client handshake, tools/list, and tools/call lifecycle."""
    mock_responses = [
        # Handshake initialize response
        {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "protocolVersion": "2024-11-05",
                "serverInfo": {"name": "MockServer", "version": "1.0"},
            },
        },
        # tools/list response
        {
            "jsonrpc": "2.0",
            "id": 2,
            "result": {
                "tools": [
                    {
                        "name": "greet",
                        "description": "Greet user by name",
                        "inputSchema": {
                            "type": "object",
                            "properties": {"name": {"type": "string"}},
                            "required": ["name"],
                        },
                    }
                ]
            },
        },
        # tools/call response
        {
            "jsonrpc": "2.0",
            "id": 3,
            "result": {
                "content": [{"type": "text", "text": "Hello, NexusAI!"}],
                "isError": False,
            },
        },
        # ping response
        {
            "jsonrpc": "2.0",
            "id": 4,
            "result": {},
        },
    ]

    fake_reader = FakeStreamReader(mock_responses)
    fake_writer = FakeStreamWriter()

    mock_process = MagicMock()
    mock_process.stdin = fake_writer
    mock_process.stdout = fake_reader
    mock_process.returncode = None
    mock_process.terminate = MagicMock()
    mock_process.wait = AsyncMock(return_value=0)

    client = McpClient(sample_config)

    with patch("asyncio.create_subprocess_exec", return_value=mock_process):
        await client.start()
        assert client.is_connected is True
        assert client.server_name == "test_server"

        # List tools
        tools = await client.list_tools()
        assert len(tools) == 1
        assert tools[0].name == "greet"
        assert tools[0].description == "Greet user by name"

        # Call tool
        result = await client.call_tool("greet", {"name": "NexusAI"})
        assert not result.is_error
        assert result.extract_text() == "Hello, NexusAI!"

        # Ping
        is_alive = await client.ping()
        assert is_alive

        # Stop
        await client.stop()
        assert not client.is_connected


@pytest.mark.asyncio
async def test_mcp_client_server_error_response(sample_config: McpServerConfig) -> None:
    """Verify that JSON-RPC error response from server raises ToolExecutionError."""
    mock_responses = [
        # Handshake initialize response
        {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {"serverInfo": {"name": "MockServer"}},
        },
        # tools/call error response
        {
            "jsonrpc": "2.0",
            "id": 2,
            "error": {"code": -32000, "message": "Database query failed"},
        },
    ]

    fake_reader = FakeStreamReader(mock_responses)
    fake_writer = FakeStreamWriter()

    mock_process = MagicMock()
    mock_process.stdin = fake_writer
    mock_process.stdout = fake_reader
    mock_process.returncode = None
    mock_process.terminate = MagicMock()
    mock_process.wait = AsyncMock(return_value=0)

    client = McpClient(sample_config)

    with patch("asyncio.create_subprocess_exec", return_value=mock_process):
        await client.start()
        with pytest.raises(ToolExecutionError) as exc_info:
            await client.call_tool("faulty_tool", {})

        assert "Database query failed" in str(exc_info.value)
        await client.stop()


@pytest.mark.asyncio
async def test_mcp_client_timeout_handling(sample_config: McpServerConfig) -> None:
    """Verify that timeouts are handled cleanly without hanging."""
    sample_config.timeout_seconds = 0.1

    # Only provide handshake response; next request will timeout
    mock_responses = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {"serverInfo": {"name": "MockServer"}},
        },
    ]

    fake_reader = FakeStreamReader(mock_responses)
    fake_writer = FakeStreamWriter()

    mock_process = MagicMock()
    mock_process.stdin = fake_writer
    mock_process.stdout = fake_reader
    mock_process.returncode = None
    mock_process.terminate = MagicMock()
    mock_process.wait = AsyncMock(return_value=0)

    client = McpClient(sample_config)

    with patch("asyncio.create_subprocess_exec", return_value=mock_process):
        await client.start()
        with pytest.raises(ToolExecutionError) as exc_info:
            await client.list_tools()

        assert "Timeout waiting for response" in str(exc_info.value)
        await client.stop()
