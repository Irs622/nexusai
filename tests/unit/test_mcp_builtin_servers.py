"""Unit and integration tests for NexusAI Built-in MCP Server Pack (Filesystem, SQLite, Web Fetcher)."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from nexusai.security.guard import RiskLevel
from nexusai.tools.mcp.client import McpClient
from nexusai.tools.mcp.models import McpServerConfig
from nexusai.tools.mcp.servers.base import McpServerBase
from nexusai.tools.mcp.servers.filesystem import FilesystemMcpServer
from nexusai.tools.mcp.servers.sqlite import SqliteMcpServer
from nexusai.tools.mcp.servers.web_fetcher import WebFetcherMcpServer


@pytest.mark.unit
@pytest.mark.asyncio
async def test_mcp_server_base_lifecycle() -> None:
    """Verify base JSON-RPC 2.0 handshake, ping, tools/list, and tools/call handling."""
    server = McpServerBase(name="test-server", version="2.1.0")

    def echo_handler(args: dict[str, Any]) -> str:
        return f"Echo: {args.get('text', '')}"

    server.register_tool(
        name="echo",
        description="Echo input text",
        input_schema={"type": "object", "properties": {"text": {"type": "string"}}},
        handler=echo_handler,
    )

    # 1. Initialize
    init_res = await server.handle_request(
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
    )
    assert init_res is not None
    assert init_res["result"]["serverInfo"]["name"] == "test-server"
    assert init_res["result"]["serverInfo"]["version"] == "2.1.0"
    assert "tools" in init_res["result"]["capabilities"]

    # 2. Notifications/initialized
    notify_res = await server.handle_request(
        {"jsonrpc": "2.0", "method": "notifications/initialized"}
    )
    assert notify_res is None
    assert server._is_initialized is True

    # 3. Ping
    ping_res = await server.handle_request({"jsonrpc": "2.0", "id": 2, "method": "ping"})
    assert ping_res is not None
    assert ping_res["result"] == {}

    # 4. Tools/list
    list_res = await server.handle_request({"jsonrpc": "2.0", "id": 3, "method": "tools/list"})
    assert list_res is not None
    tools = list_res["result"]["tools"]
    assert len(tools) == 1
    assert tools[0]["name"] == "echo"

    # 5. Tools/call success
    call_res = await server.handle_request(
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "echo", "arguments": {"text": "nexus"}},
        }
    )
    assert call_res is not None
    assert call_res["result"]["isError"] is False
    assert "Echo: nexus" in call_res["result"]["content"][0]["text"]

    # 6. Tools/call nonexistent tool
    missing_call = await server.handle_request(
        {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {"name": "nonexistent"},
        }
    )
    assert missing_call is not None
    assert "error" in missing_call
    assert missing_call["error"]["code"] == -32601

    # 7. Unknown method
    unknown_method = await server.handle_request(
        {"jsonrpc": "2.0", "id": 6, "method": "some_random_method"}
    )
    assert unknown_method is not None
    assert unknown_method["error"]["code"] == -32601


@pytest.mark.unit
@pytest.mark.asyncio
async def test_filesystem_mcp_server(tmp_path: Path) -> None:
    """Verify sandboxed filesystem operations and jail enforcement."""
    sandbox_root = tmp_path / "sandbox"
    server = FilesystemMcpServer(root_dir=sandbox_root)

    # 1. Write file
    write_res = await server.handle_request(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "write_file",
                "arguments": {"path": "docs/note.txt", "content": "NexusAI Second Brain"},
            },
        }
    )
    assert write_res is not None
    assert write_res["result"]["isError"] is False
    assert (sandbox_root / "docs" / "note.txt").exists()

    # 2. Read file
    read_res = await server.handle_request(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "read_file", "arguments": {"path": "docs/note.txt"}},
        }
    )
    assert read_res is not None
    assert read_res["result"]["isError"] is False
    assert "NexusAI Second Brain" in read_res["result"]["content"][0]["text"]

    # 3. Get file info
    info_res = await server.handle_request(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "get_file_info", "arguments": {"path": "docs/note.txt"}},
        }
    )
    assert info_res is not None
    assert info_res["result"]["isError"] is False
    assert "note.txt" in info_res["result"]["content"][0]["text"]

    # 4. List directory
    list_res = await server.handle_request(
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "list_directory", "arguments": {"path": "docs"}},
        }
    )
    assert list_res is not None
    assert list_res["result"]["isError"] is False
    assert "note.txt" in list_res["result"]["content"][0]["text"]

    # 5. Search files
    search_res = await server.handle_request(
        {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {
                "name": "search_files",
                "arguments": {"pattern": "*.txt", "path": "docs"},
            },
        }
    )
    assert search_res is not None
    assert search_res["result"]["isError"] is False
    assert "note.txt" in search_res["result"]["content"][0]["text"]

    # 6. Jail Boundary Enforcement (Path Traversal attempt)
    jail_res = await server.handle_request(
        {
            "jsonrpc": "2.0",
            "id": 6,
            "method": "tools/call",
            "params": {
                "name": "read_file",
                "arguments": {"path": "../../etc/shadow"},
            },
        }
    )
    assert jail_res is not None
    assert jail_res["result"]["isError"] is True
    assert "Path traversal denied" in jail_res["result"]["content"][0]["text"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_sqlite_mcp_server(tmp_path: Path) -> None:
    """Verify SQLite query execution, transaction commit, and schema inspection."""
    db_file = tmp_path / "test.db"
    server = SqliteMcpServer(db_path=db_file)

    # 1. Create table
    create_res = await server.handle_request(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "write_query",
                "arguments": {
                    "query": "CREATE TABLE workers (id INTEGER PRIMARY KEY, name TEXT, capability TEXT);"
                },
            },
        }
    )
    assert create_res is not None
    assert create_res["result"]["isError"] is False

    # 2. Insert records with parameters
    insert_res = await server.handle_request(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "write_query",
                "arguments": {
                    "query": "INSERT INTO workers (name, capability) VALUES (?, ?);",
                    "params": ["Worker-Alpha", "gpu_inference"],
                },
            },
        }
    )
    assert insert_res is not None
    assert insert_res["result"]["isError"] is False
    assert "rows_affected" in insert_res["result"]["content"][0]["text"]

    # 3. Read query
    select_res = await server.handle_request(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "read_query",
                "arguments": {
                    "query": "SELECT * FROM workers WHERE capability = ?;",
                    "params": ["gpu_inference"],
                },
            },
        }
    )
    assert select_res is not None
    assert select_res["result"]["isError"] is False
    assert "Worker-Alpha" in select_res["result"]["content"][0]["text"]

    # 4. List tables
    tables_res = await server.handle_request(
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "list_tables", "arguments": {}},
        }
    )
    assert tables_res is not None
    assert tables_res["result"]["isError"] is False
    assert "workers" in tables_res["result"]["content"][0]["text"]

    # 5. Describe table
    desc_res = await server.handle_request(
        {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {
                "name": "describe_table",
                "arguments": {"table_name": "workers"},
            },
        }
    )
    assert desc_res is not None
    assert desc_res["result"]["isError"] is False
    assert "capability" in desc_res["result"]["content"][0]["text"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_web_fetcher_mcp_server() -> None:
    """Verify Web Fetcher HTML extraction and HTTP request handling."""
    server = WebFetcherMcpServer()

    mock_html = """
    <!DOCTYPE html>
    <html>
        <head><title>NexusAI Platform</title></head>
        <body>
            <style>.hide { display: none; }</style>
            <h1>Autonomous Agent Architecture</h1>
            <p>NexusAI provides production-grade resilience.</p>
            <script>alert('attack');</script>
        </body>
    </html>
    """

    mock_resp = httpx.Response(
        status_code=200,
        headers={"content-type": "text/html; charset=utf-8"},
        text=mock_html,
        request=httpx.Request("GET", "https://nexusai.local/docs"),
    )

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp

        fetch_res = await server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "fetch_url",
                    "arguments": {"url": "https://nexusai.local/docs"},
                },
            }
        )
        assert fetch_res is not None
        assert fetch_res["result"]["isError"] is False
        content_text = fetch_res["result"]["content"][0]["text"]
        assert "NexusAI Platform" in content_text
        assert "Autonomous Agent Architecture" in content_text
        assert "<script>" not in content_text
        assert "alert(" not in content_text

    # Generic HTTP request test
    mock_post_resp = httpx.Response(
        status_code=201,
        headers={"content-type": "application/json"},
        text='{"status": "created", "id": "task_100"}',
        request=httpx.Request("POST", "https://api.nexusai.local/tasks"),
    )

    with patch("httpx.AsyncClient.request", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = mock_post_resp

        req_res = await server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "http_request",
                    "arguments": {
                        "method": "POST",
                        "url": "https://api.nexusai.local/tasks",
                        "body": '{"title": "analyze"}',
                    },
                },
            }
        )
        assert req_res is not None
        assert req_res["result"]["isError"] is False
        assert "task_100" in req_res["result"]["content"][0]["text"]


@pytest.mark.asyncio
async def test_end_to_end_mcp_client_with_builtin_server(tmp_path: Path) -> None:
    """Verify live subprocess execution and stdio transport between McpClient and SqliteMcpServer."""
    db_file = tmp_path / "live_cluster.db"
    server_config = McpServerConfig(
        name="test_live_sqlite",
        command="python3",
        args=["-m", "nexusai.tools.mcp.servers.sqlite", "--db-path", str(db_file)],
        env={"PYTHONPATH": "src:."},
        timeout_seconds=5.0,
        risk_level=RiskLevel.MEDIUM,
    )

    client = McpClient(server_config)
    try:
        await client.start()
        assert client.is_connected is True

        # 1. Discover tools
        tools = await client.list_tools()
        tool_names = [t.name for t in tools]
        assert "write_query" in tool_names
        assert "read_query" in tool_names
        assert "list_tables" in tool_names
        assert "describe_table" in tool_names

        # 2. Call tool: write_query
        res_create = await client.call_tool(
            "write_query",
            {
                "query": "CREATE TABLE clusters (id INTEGER PRIMARY KEY, region TEXT, nodes INT);"
            },
        )
        assert not res_create.is_error

        # 3. Call tool: insert
        res_insert = await client.call_tool(
            "write_query",
            {
                "query": "INSERT INTO clusters (region, nodes) VALUES (?, ?);",
                "params": ["us-east-1", 16],
            },
        )
        assert not res_insert.is_error

        # 4. Call tool: read_query
        res_read = await client.call_tool(
            "read_query",
            {"query": "SELECT region, nodes FROM clusters WHERE region = ?;", "params": ["us-east-1"]},
        )
        assert not res_read.is_error
        assert "us-east-1" in res_read.extract_text()

    finally:
        await client.stop()
        assert not client.is_connected

