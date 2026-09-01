"""Unit tests for FastAPI server MCP management and Server-Sent Events (SSE) stream endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock

import httpx
import pytest

from nexusai.api.server import create_app
from nexusai.security.guard import RiskLevel
from nexusai.tools.mcp.models import McpServerConfig, McpToolDefinition
from nexusai.tools.mcp.tool import McpToolWrapper


@pytest.fixture
def app_instance():
    """Create test application instance with in-memory db."""
    app = create_app(db_path=":memory:")
    return app


@pytest.mark.asyncio
async def test_api_status_and_tools(app_instance) -> None:
    """Verify core /api/status and /api/tools endpoints return expected structures."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app_instance), base_url="http://test"
    ) as client:
        # Status
        res_status = await client.get("/api/status")
        assert res_status.status_code == 200
        data = res_status.json()
        assert data["status"] == "OPERATIONAL"
        assert "context" in data

        # Tools
        res_tools = await client.get("/api/tools")
        assert res_tools.status_code == 200
        tools = res_tools.json()
        assert isinstance(tools, list)
        assert len(tools) > 0


@pytest.mark.asyncio
async def test_api_mcp_endpoints(app_instance) -> None:
    """Verify MCP management endpoints (/api/mcp/servers, ping, and reload)."""
    mcp_manager = app_instance.state.mcp_manager

    # Mock register an MCP server in the manager
    mock_client = AsyncMock()
    mock_client.is_connected = True
    mock_client.ping.return_value = True

    config = McpServerConfig(name="mock_server", command="echo", args=[])
    mcp_manager.register_server_config(config)
    mcp_manager._clients["mock_server"] = mock_client

    tool = McpToolWrapper(
        client=mock_client,
        definition=McpToolDefinition(
            name="mock_mcp_tool",
            description="A mock MCP tool",
            input_schema={"type": "object", "properties": {}},
        ),
        risk_level=RiskLevel.LOW,
    )
    mcp_manager._tools_by_server["mock_server"] = [tool]

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app_instance), base_url="http://test"
    ) as client:
        # 1. List MCP servers
        res_list = await client.get("/api/mcp/servers")
        assert res_list.status_code == 200
        data = res_list.json()
        assert data["total_servers"] >= 1
        server_names = [s["name"] for s in data["servers"]]
        assert "mock_server" in server_names

        # 2. Ping MCP server
        res_ping = await client.post("/api/mcp/servers/mock_server/ping")
        assert res_ping.status_code == 200
        ping_data = res_ping.json()
        assert ping_data["server"] == "mock_server"
        assert ping_data["is_alive"] is True

        # 3. Ping unknown server -> 404
        res_404 = await client.post("/api/mcp/servers/unknown_server/ping")
        assert res_404.status_code == 404

        # 4. Reload MCP config
        res_reload = await client.post("/api/mcp/reload")
        assert res_reload.status_code == 200


@pytest.mark.asyncio
async def test_api_sse_event_stream(app_instance) -> None:
    """Verify /api/events/stream connects and streams Server-Sent Events."""
    found = False
    for route in app_instance.routes:
        if getattr(route, "path", None) == "/api/events/stream":
            resp = await route.endpoint()
            assert resp.media_type == "text/event-stream"
            first_event = await anext(resp.body_iterator)
            assert "event: handshake" in first_event
            assert "CONNECTED" in first_event
            found = True
            break

    assert found is True
