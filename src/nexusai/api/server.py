"""FastAPI Server for NexusAI Web Dashboard API, Real-Time SSE Event Stream, and Static File Serving."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import json
from pathlib import Path
import time
from typing import Any, AsyncGenerator

from dotenv import find_dotenv, load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

load_dotenv(find_dotenv(usecwd=True))

from nexusai.automation.scheduler import SchedulerService
from nexusai.brain.coordinator import BrainCoordinator
from nexusai.bus.bus import CommandBus, EventBus
from nexusai.bus.commands import ExecuteToolCommand, ExecuteToolCommandHandler
from nexusai.context.engine import ContextEngine
from nexusai.core.config import SystemConfig
from nexusai.core.errors import ConfigurationError
from nexusai.logging.logger import logger
from nexusai.memory.sqlite_memory import SQLiteMemory
from nexusai.models.openai_provider import OpenAIProvider
from nexusai.security.guard import SecurityGuard

# Import Tools & MCP
from nexusai.tools.automation import ScheduleReminderTool
from nexusai.tools.knowledge import RecallFactTool, RememberFactTool, VectorKnowledgeBase
from nexusai.tools.macos import GetActiveWindowTool, NotifyTool, OpenAppTool, RawAppleScriptTool
from nexusai.tools.mcp import McpServerManager
from nexusai.tools.registry import ToolRegistry
from nexusai.tools.system import TerminalTool
from nexusai.tools.vision import ScreenCaptureTool
from nexusai.tools.workspace import GitStatusTool, ListDirectoryTool, ReadFileTool

web_dir = Path(__file__).resolve().parent.parent.parent.parent / "web"


# Request Schemas
class ChatRequest(BaseModel):
    prompt: str = Field(..., description="User prompt text")
    session_id: str = Field("web_session", description="Session ID")
    user_confirmed: bool = Field(False, description="Security confirmation flag")


class ToolExecRequest(BaseModel):
    tool_name: str = Field(..., description="Name of tool to execute")
    arguments: dict[str, Any] = Field(default_factory=dict, description="Tool parameters")
    user_confirmed: bool = Field(False, description="User confirmation flag")


ChatRequest.model_rebuild()
ToolExecRequest.model_rebuild()


def create_app(
    db_path: str = ":memory:",
    vector_kb: VectorKnowledgeBase | None = None,
    scheduler: SchedulerService | None = None,
) -> FastAPI:
    """Create and configure FastAPI application for NexusAI Web Dashboard."""

    # Initialize Core Services
    config = SystemConfig.load_from_yaml()
    security_guard = SecurityGuard(config.security)
    event_bus = EventBus()
    command_bus = CommandBus()
    registry = ToolRegistry()
    context_engine = ContextEngine()
    sched_service = scheduler or SchedulerService()
    mcp_manager = McpServerManager(tool_registry=registry)

    # Register default builtin tools
    registry.register(TerminalTool())
    registry.register(OpenAppTool())
    registry.register(GetActiveWindowTool())
    registry.register(RawAppleScriptTool())
    registry.register(NotifyTool())
    registry.register(ScheduleReminderTool(scheduler=sched_service))
    registry.register(ListDirectoryTool())
    registry.register(ReadFileTool())
    registry.register(GitStatusTool())
    registry.register(ScreenCaptureTool())

    if vector_kb:
        registry.register(RememberFactTool(vector_kb=vector_kb))
        registry.register(RecallFactTool(vector_kb=vector_kb))
    else:
        registry.register(RememberFactTool())
        registry.register(RecallFactTool())

    # Handler
    handler = ExecuteToolCommandHandler(registry, security_guard, event_bus)
    command_bus.register(ExecuteToolCommand, handler)

    # Memory & Coordinator
    memory = SQLiteMemory(db_path=db_path)
    try:
        provider = OpenAIProvider(settings=config.models)
    except ConfigurationError:
        provider = None
    coordinator = BrainCoordinator(
        model_provider=provider,
        registry=registry,
        command_bus=command_bus,
        memory=memory,
        context_engine=context_engine,
    )

    @asynccontextmanager
    async def lifespan(app_instance: FastAPI) -> AsyncGenerator[None, None]:
        await memory.initialize_db()
        sched_service.start()

        # Load MCP configuration if present
        mcp_cfg_path = Path("config/mcp_servers.yaml")
        if mcp_cfg_path.exists():
            try:
                mcp_manager.load_config_file(mcp_cfg_path)
                await mcp_manager.start_all()
                logger.info(f"Loaded MCP servers from {mcp_cfg_path}")
            except Exception as err:
                logger.warning(f"Failed loading MCP config on startup: {err}")

        yield

        sched_service.stop()
        await mcp_manager.stop_all()

    app = FastAPI(
        title="NexusAI Web Operating System Dashboard",
        description="Web UI and API Gateway for NexusAI Agentic OS with Real-Time SSE Stream & MCP",
        version="0.2.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Attach manager to app state for testing and direct access
    app.state.mcp_manager = mcp_manager
    app.state.registry = registry

    # =========================================================================
    # CORE REST ENDPOINTS
    # =========================================================================

    @app.get("/api/status")
    async def get_status() -> dict[str, Any]:
        working_ctx = await context_engine.gather_context()
        return {
            "status": "OPERATIONAL",
            "environment": config.app.environment,
            "default_model": f"{config.models.default_provider}/{config.models.default_model}",
            "strict_security": config.security.strict_mode,
            "context": working_ctx.model_dump(),
        }

    @app.get("/api/tools")
    async def get_tools() -> list[dict[str, Any]]:
        schemas = registry.get_all_schemas()
        tools_info = []
        for schema in schemas:
            func = schema["function"]
            tool_name = func["name"]
            tool_obj = registry.get(tool_name)
            tools_info.append(
                {
                    "name": tool_name,
                    "description": func["description"],
                    "risk_level": tool_obj.risk_level.value,
                    "parameters": func["parameters"],
                }
            )
        return tools_info

    @app.post("/api/chat")
    async def chat_endpoint(req: ChatRequest) -> dict[str, Any]:
        try:
            res = await coordinator.process_user_input(
                user_text=req.prompt,
                session_id=req.session_id,
                user_confirmed=req.user_confirmed,
            )
            return res
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e)) from e

    @app.post("/api/tools/execute")
    async def execute_tool_endpoint(req: ToolExecRequest) -> dict[str, Any]:
        try:
            cmd = ExecuteToolCommand(
                tool_name=req.tool_name,
                arguments=req.arguments,
                user_confirmed=req.user_confirmed,
            )
            output = await command_bus.dispatch(cmd)
            return {"success": True, "tool_name": req.tool_name, "output": output}
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

    # =========================================================================
    # MODEL CONTEXT PROTOCOL (MCP) ENDPOINTS
    # =========================================================================

    @app.get("/api/mcp/servers")
    async def list_mcp_servers() -> dict[str, Any]:
        """List all configured MCP servers, connection status, and discovered tools."""
        servers = [
            mcp_manager.get_server_info(name) for name in mcp_manager.configured_server_names
        ]
        return {"total_servers": len(servers), "servers": servers}

    @app.post("/api/mcp/servers/{server_name}/ping")
    async def ping_mcp_server(server_name: str) -> dict[str, Any]:
        """Ping a specific MCP server to check liveliness."""
        try:
            is_alive = await mcp_manager.ping_server(server_name)
            return {"server": server_name, "is_alive": is_alive}
        except Exception as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    @app.post("/api/mcp/reload")
    async def reload_mcp_config() -> dict[str, Any]:
        """Reload MCP declarative configuration file."""
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
            raise HTTPException(status_code=500, detail=str(e)) from e

    # =========================================================================
    # REAL-TIME SERVER-SENT EVENTS (SSE) ENDPOINT
    # =========================================================================

    @app.get("/api/events/stream")
    async def sse_stream() -> StreamingResponse:
        """Stream real-time system telemetry and agent OS events via Server-Sent Events."""

        async def event_generator() -> AsyncGenerator[str, None]:
            # Initial handshake event
            init_payload = json.dumps(
                {
                    "type": "handshake",
                    "status": "CONNECTED",
                    "timestamp": time.time(),
                    "server": "NexusAI-WebOS",
                }
            )
            yield f"event: handshake\ndata: {init_payload}\n\n"

            while True:
                try:
                    ctx = await context_engine.gather_context()
                    telemetry_payload = json.dumps(
                        {
                            "type": "telemetry",
                            "timestamp": time.time(),
                            "active_app": ctx.active_application,
                            "active_title": ctx.active_window_title,
                            "git_branch": ctx.git_branch,
                            "cpu": round(ctx.cpu_usage_percent, 1),
                            "ram": round(ctx.memory_usage_percent, 1),
                        }
                    )
                    yield f"event: telemetry\ndata: {telemetry_payload}\n\n"
                    await asyncio.sleep(2.0)
                except asyncio.CancelledError:
                    break
                except Exception:
                    await asyncio.sleep(3.0)

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    # =========================================================================
    # STATIC FILE SERVING
    # =========================================================================

    if web_dir.exists():
        app.mount("/static", StaticFiles(directory=str(web_dir)), name="static")

        @app.get("/")
        async def serve_index() -> FileResponse:
            return FileResponse(web_dir / "index.html")

    return app


app = create_app()
