"""McpServerManager coordinating multi-server lifecycle, ToolRegistry, and CapabilityDiscovery."""

from __future__ import annotations

import pathlib
from typing import Any

import yaml

from nexusai.brain.ports.capability_discovery import (
    CapabilityAdvertisement,
    RuntimeCapabilityDiscovery,
)
from nexusai.core.errors import ToolExecutionError
from nexusai.logging.logger import logger
from nexusai.tools.mcp.client import McpClient
from nexusai.tools.mcp.models import McpServerConfig
from nexusai.tools.mcp.tool import McpToolWrapper
from nexusai.tools.registry import ToolRegistry


class McpServerManager:
    """Coordinates lifecycle of multiple MCP servers, tool registration, and capability discovery."""

    def __init__(
        self,
        tool_registry: ToolRegistry | None = None,
        capability_discovery: RuntimeCapabilityDiscovery | None = None,
        namespace_tools: bool = False,
    ) -> None:
        self.tool_registry = tool_registry
        self.capability_discovery = capability_discovery
        self.namespace_tools = namespace_tools

        self._server_configs: dict[str, McpServerConfig] = {}
        self._clients: dict[str, McpClient] = {}
        self._tools_by_server: dict[str, list[McpToolWrapper]] = {}

    @property
    def registered_server_names(self) -> list[str]:
        """Return list of all configured server names."""
        return list(self._server_configs.keys())

    @property
    def configured_server_names(self) -> list[str]:
        """Alias for registered_server_names."""
        return list(self._server_configs.keys())

    @property
    def connected_server_names(self) -> list[str]:
        """Return list of currently active and connected server names."""
        return [name for name, client in self._clients.items() if client.is_connected]

    def register_server_config(self, config: McpServerConfig) -> None:
        """Register a server configuration without immediate connection."""
        self._server_configs[config.name] = config

    def load_config_file(self, config_path: str | pathlib.Path) -> int:
        """Load and parse server configurations from a YAML file.

        Returns number of server configurations loaded.
        """
        path = pathlib.Path(config_path)
        if not path.is_file():
            logger.warning(f"[McpServerManager] Configuration file not found: {path}")
            return 0

        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        servers_data = data.get("mcp_servers", {})
        loaded_count = 0

        for name, entry in servers_data.items():
            if not isinstance(entry, dict):
                continue
            entry_dict = dict(entry)
            entry_dict["name"] = name
            try:
                config = McpServerConfig.model_validate(entry_dict)
                self.register_server_config(config)
                loaded_count += 1
            except Exception as e:
                logger.error(f"[McpServerManager] Failed to parse config for server '{name}': {e}")

        logger.info(f"[McpServerManager] Loaded {loaded_count} server configs from {path}")
        return loaded_count

    async def connect_server(self, server_name: str) -> list[McpToolWrapper]:
        """Connect to a specific configured MCP server, discover its tools, and register them."""
        if server_name not in self._server_configs:
            raise ToolExecutionError(f"MCP server '{server_name}' configuration not found")

        config = self._server_configs[server_name]
        if not config.enabled:
            logger.info(f"[McpServerManager] Server '{server_name}' is disabled; skipping")
            return []

        # If already connected, return existing tools
        if server_name in self._clients and self._clients[server_name].is_connected:
            return self._tools_by_server.get(server_name, [])

        client = McpClient(config)
        try:
            await client.start()
        except Exception as e:
            logger.error(f"[McpServerManager] Failed to start client for '{server_name}': {e}")
            raise

        self._clients[server_name] = client

        # Discover tools
        try:
            definitions = await client.list_tools()
        except Exception as e:
            logger.error(f"[McpServerManager] Failed to discover tools from '{server_name}': {e}")
            await client.stop()
            self._clients.pop(server_name, None)
            raise

        prefix = server_name if self.namespace_tools else None
        discovered_tools: list[McpToolWrapper] = []

        for defn in definitions:
            wrapper = McpToolWrapper(
                client=client,
                definition=defn,
                risk_level=config.risk_level,
                namespace_prefix=prefix,
            )
            discovered_tools.append(wrapper)

            # Register into ToolRegistry
            if self.tool_registry is not None:
                try:
                    self.tool_registry.register(wrapper)
                    logger.debug(
                        f"[McpServerManager] Registered MCP tool '{wrapper.name}' in ToolRegistry"
                    )
                except Exception as reg_err:
                    logger.warning(
                        f"[McpServerManager] Could not register '{wrapper.name}' into registry: {reg_err}"
                    )

            # Publish into RuntimeCapabilityDiscovery
            if self.capability_discovery is not None:
                try:
                    advertisement = CapabilityAdvertisement(
                        capability_name=wrapper.name,
                        provider_name=f"MCP:{server_name}",
                        tool_name=wrapper.name,
                        quality_score=0.95,
                    )
                    self.capability_discovery.publish_capability(advertisement)
                    logger.debug(
                        f"[McpServerManager] Published capability '{wrapper.name}' to RuntimeCapabilityDiscovery"
                    )
                except Exception as cap_err:
                    logger.warning(
                        f"[McpServerManager] Could not publish capability for '{wrapper.name}': {cap_err}"
                    )

        self._tools_by_server[server_name] = discovered_tools
        logger.info(
            f"[McpServerManager] Connected to '{server_name}' and registered {len(discovered_tools)} tools"
        )
        return discovered_tools

    async def disconnect_server(self, server_name: str) -> None:
        """Disconnect an MCP server and cleanly unregister its tools and capabilities."""
        tools = self._tools_by_server.pop(server_name, [])

        for tool in tools:
            # Revoke from capability discovery
            if self.capability_discovery is not None:
                try:
                    self.capability_discovery.revoke_capability(tool.name)
                except Exception as e:
                    logger.warning(
                        f"[McpServerManager] Error revoking capability '{tool.name}': {e}"
                    )

            # Unregister from tool registry
            if self.tool_registry is not None:
                if hasattr(self.tool_registry, "unregister"):
                    self.tool_registry.unregister(tool.name)
                elif (
                    hasattr(self.tool_registry, "_tools") and tool.name in self.tool_registry._tools
                ):
                    del self.tool_registry._tools[tool.name]

        client = self._clients.pop(server_name, None)
        if client:
            await client.stop()

        logger.info(
            f"[McpServerManager] Disconnected server '{server_name}' and revoked {len(tools)} tools"
        )

    async def start_all(self) -> dict[str, list[McpToolWrapper]]:
        """Start and connect all registered and enabled MCP servers."""
        results: dict[str, list[McpToolWrapper]] = {}
        for server_name, config in self._server_configs.items():
            if config.enabled:
                try:
                    tools = await self.connect_server(server_name)
                    results[server_name] = tools
                except Exception as err:
                    logger.error(f"[McpServerManager] Error starting server '{server_name}': {err}")
        return results

    async def stop_all(self) -> None:
        """Disconnect and stop all connected MCP servers."""
        for server_name in list(self._clients.keys()):
            try:
                await self.disconnect_server(server_name)
            except Exception as e:
                logger.error(f"[McpServerManager] Error disconnecting '{server_name}': {e}")

    def get_all_tools(self) -> list[McpToolWrapper]:
        """Return all active tools across all connected servers."""
        all_tools: list[McpToolWrapper] = []
        for tools in self._tools_by_server.values():
            all_tools.extend(tools)
        return all_tools

    async def ping_server(self, server_name: str) -> bool:
        """Ping a connected MCP server."""
        if server_name not in self._clients:
            raise ToolExecutionError(f"MCP server '{server_name}' is not connected")
        return await self._clients[server_name].ping()

    def get_server_info(self, server_name: str) -> dict[str, Any]:
        """Return information about a registered MCP server."""
        cfg = self._server_configs.get(server_name)
        client = self._clients.get(server_name)
        tools = self._tools_by_server.get(server_name, [])
        return {
            "name": server_name,
            "is_connected": client.is_connected if client else False,
            "command": cfg.command if cfg else "",
            "tools_count": len(tools),
            "tools": [
                {
                    "name": t.name,
                    "description": t.description,
                    "risk_level": t.risk_level.value,
                }
                for t in tools
            ],
        }
