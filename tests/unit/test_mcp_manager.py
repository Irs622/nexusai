"""Unit tests for McpServerManager, ToolRegistry integration, and RuntimeCapabilityDiscovery."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from nexusai.brain.ports.capability_discovery import RuntimeCapabilityDiscovery
from nexusai.security.guard import RiskLevel
from nexusai.tools.mcp.manager import McpServerManager
from nexusai.tools.mcp.models import McpServerConfig, McpToolDefinition
from nexusai.tools.registry import ToolRegistry


@pytest.fixture
def tool_registry() -> ToolRegistry:
    return ToolRegistry()


@pytest.fixture
def capability_discovery() -> RuntimeCapabilityDiscovery:
    return RuntimeCapabilityDiscovery()


@pytest.mark.asyncio
async def test_mcp_manager_connect_and_disconnect(
    tool_registry: ToolRegistry,
    capability_discovery: RuntimeCapabilityDiscovery,
) -> None:
    """Verify end-to-end integration between McpServerManager, ToolRegistry, and CapabilityDiscovery."""
    manager = McpServerManager(
        tool_registry=tool_registry,
        capability_discovery=capability_discovery,
    )

    config = McpServerConfig(
        name="test_fs",
        command="python3",
        args=["-m", "fs_server"],
        enabled=True,
        risk_level=RiskLevel.LOW,
    )
    manager.register_server_config(config)

    mock_tools = [
        McpToolDefinition(
            name="fs_read",
            description="Read file contents",
            inputSchema={"type": "object", "properties": {"path": {"type": "string"}}},
        )
    ]

    with patch("nexusai.tools.mcp.manager.McpClient") as MockClientCls:
        mock_client_instance = MockClientCls.return_value
        mock_client_instance.start = AsyncMock()
        mock_client_instance.stop = AsyncMock()
        mock_client_instance.list_tools = AsyncMock(return_value=mock_tools)
        mock_client_instance.is_connected = True
        mock_client_instance.server_name = "test_fs"

        # 1. Connect server
        tools = await manager.connect_server("test_fs")
        assert len(tools) == 1
        assert tools[0].name == "fs_read"

        # 2. Check ToolRegistry
        assert tool_registry.has_tool("fs_read") is True

        # 3. Check RuntimeCapabilityDiscovery
        active_caps = capability_discovery.get_active_capabilities()
        cap_names = [c.capability_name for c in active_caps]
        assert "fs_read" in cap_names

        # 4. Disconnect server
        await manager.disconnect_server("test_fs")
        assert tool_registry.has_tool("fs_read") is False

        # Verify capability revoked
        active_caps_after = capability_discovery.get_active_capabilities()
        cap_names_after = [c.capability_name for c in active_caps_after]
        assert "fs_read" not in cap_names_after
        mock_client_instance.stop.assert_awaited_once()


def test_mcp_manager_load_yaml_config(tmp_path: object) -> None:
    """Verify loading server configs from a YAML file."""
    import pathlib

    yaml_content = """
mcp_servers:
  sqlite_prod:
    command: "uvx"
    args: ["mcp-server-sqlite", "--db", "prod.db"]
    enabled: true
    risk_level: "MEDIUM"
    timeout_seconds: 45.0
  fs_local:
    command: "npx"
    args: ["@modelcontextprotocol/server-filesystem", "/tmp"]
    enabled: false
    risk_level: "HIGH"
"""
    p = pathlib.Path(str(tmp_path)) / "mcp.yaml"
    p.write_text(yaml_content, encoding="utf-8")

    manager = McpServerManager()
    count = manager.load_config_file(p)
    assert count == 2
    assert "sqlite_prod" in manager.registered_server_names
    assert "fs_local" in manager.registered_server_names

    cfg1 = manager._server_configs["sqlite_prod"]
    assert cfg1.command == "uvx"
    assert cfg1.timeout_seconds == 45.0
    assert cfg1.enabled is True

    cfg2 = manager._server_configs["fs_local"]
    assert cfg2.enabled is False
    assert cfg2.risk_level == RiskLevel.HIGH
