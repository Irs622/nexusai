"""
FastAPI Server for NexusAI Web Dashboard API & Static File Serving.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException

load_dotenv()
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from nexusai.automation.scheduler import SchedulerService
from nexusai.brain.coordinator import BrainCoordinator
from nexusai.bus.bus import CommandBus, EventBus
from nexusai.bus.commands import ExecuteToolCommand, ExecuteToolCommandHandler
from nexusai.context.engine import ContextEngine
from nexusai.core.config import SystemConfig
from nexusai.core.errors import ConfigurationError
from nexusai.memory.sqlite_memory import SQLiteMemory
from nexusai.models.openai_provider import OpenAIProvider
from nexusai.security.guard import SecurityGuard

# Import Tools
from nexusai.tools.automation import ScheduleReminderTool
from nexusai.tools.knowledge import RecallFactTool, RememberFactTool, VectorKnowledgeBase
from nexusai.tools.macos import GetActiveWindowTool, NotifyTool, OpenAppTool, RawAppleScriptTool
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


def create_app(
    db_path: str = ":memory:",
    vector_kb: VectorKnowledgeBase | None = None,
    scheduler: SchedulerService | None = None,
) -> FastAPI:
    """Create and configure FastAPI application for NexusAI Web Dashboard."""
    from contextlib import asynccontextmanager
    from typing import AsyncGenerator

    @asynccontextmanager
    async def lifespan(app_instance: FastAPI) -> AsyncGenerator[None, None]:
        await memory.initialize_db()
        sched_service.start()
        yield
        sched_service.stop()

    app = FastAPI(
        title="NexusAI Web Operating System Dashboard",
        description="Web UI and API Gateway for NexusAI Agentic OS",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Initialize Core Services
    config = SystemConfig.load_from_yaml()
    security_guard = SecurityGuard(config.security)
    event_bus = EventBus()
    command_bus = CommandBus()
    registry = ToolRegistry()
    context_engine = ContextEngine()
    sched_service = scheduler or SchedulerService()

    # Register default tools
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
        provider = OpenAIProvider(settings=config.models, api_key="")
    coordinator = BrainCoordinator(
        model_provider=provider,
        registry=registry,
        command_bus=command_bus,
        memory=memory,
        context_engine=context_engine,
    )

    # API Endpoints
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
            tools_info.append({
                "name": tool_name,
                "description": func["description"],
                "risk_level": tool_obj.risk_level.value,
                "parameters": func["parameters"],
            })
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

    # Serve Web UI
    if web_dir.exists():
        app.mount("/static", StaticFiles(directory=str(web_dir)), name="static")

        @app.get("/")
        async def serve_index() -> FileResponse:
            return FileResponse(web_dir / "index.html")

    return app


app = create_app()
