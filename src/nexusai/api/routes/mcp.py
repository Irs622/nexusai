"""Model Context Protocol server management endpoints."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from nexusai.api.common import internal_error
from nexusai.api.context import ServerContext
from nexusai.security.identity import Identity, Role, TenantContext

# Import Tools & MCP


def build_router(ctx: ServerContext) -> APIRouter:
    """Create the router for this endpoint group bound to ``ctx`` services."""
    router = APIRouter()
    mcp_manager = ctx.mcp_manager

    # =========================================================================
    # MODEL CONTEXT PROTOCOL (MCP) ENDPOINTS
    # =========================================================================

    @router.get("/api/mcp/servers")
    async def list_mcp_servers(request: Request) -> dict[str, Any]:
        """List all configured MCP servers, connection status, and discovered tools."""
        servers = [
            mcp_manager.get_server_info(name) for name in mcp_manager.configured_server_names
        ]
        return {"total_servers": len(servers), "servers": servers}

    @router.post("/api/mcp/servers/{server_name}/ping")
    async def ping_mcp_server(server_name: str, request: Request) -> dict[str, Any]:
        """Ping a specific MCP server to check liveliness."""
        identity: Identity | None = (
            getattr(request.state, "identity", None) or TenantContext.get_current_identity()
        )
        if identity and identity.role == Role.VIEWER:
            raise HTTPException(
                status_code=403,
                detail=f"RBAC access denied: Role '{identity.role.value}' cannot ping MCP servers. Operator or Admin required.",
            )
        try:
            is_alive = await mcp_manager.ping_server(server_name)
            return {"server": server_name, "is_alive": is_alive}
        except Exception as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    @router.post("/api/mcp/reload")
    async def reload_mcp_config(request: Request) -> dict[str, Any]:
        """Reload MCP declarative configuration file."""
        identity: Identity | None = (
            getattr(request.state, "identity", None) or TenantContext.get_current_identity()
        )
        if identity and identity.role not in (Role.ADMIN, Role.SYSTEM):
            raise HTTPException(
                status_code=403,
                detail=f"RBAC access denied: Role '{identity.role.value}' cannot reload MCP configuration. Admin role required.",
            )
        mcp_cfg_path = Path("config/mcp_servers.yaml")
        if not mcp_cfg_path.exists():
            return {"status": "NO_CONFIG_FILE", "message": f"{mcp_cfg_path} not found"}

        try:
            count = mcp_manager.load_config_file(mcp_cfg_path)
            await mcp_manager.start_all()
            return {
                "status": "RELOADED",
                "total_servers": count,
            }
        except Exception as e:
            raise internal_error("/api/mcp/reload", e) from e

    return router
