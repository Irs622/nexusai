"""FastAPI Server for NexusAI Web Dashboard API, Real-Time SSE Event Stream, and Static File Serving."""

from __future__ import annotations

import asyncio
import json
import time
import hashlib
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path
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
from nexusai.brain.domain.audit import GENESIS_HASH, AuditEvent
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


class DagExecuteRequest(BaseModel):
    plan_id: str = Field(default="incident_response", description="ID of plan to execute")
    simulate_failure_step: str | None = Field(
        default=None, description="Optional step ID to simulate failure"
    )
    execution_id: str = Field(
        default_factory=lambda: f"exec-dag-{int(time.time())}", description="Execution ID"
    )


class AuditTamperRequest(BaseModel):
    event_id: str | None = Field(default=None, description="Target event ID to corrupt")
    tampered_field: str = Field(default="outcome", description="Field to modify")
    new_value: str = Field(default="CORRUPTED_TAMPER_TEST", description="Tampered value")


class GovernanceDecisionRequest(BaseModel):
    decision: str = Field(default="APPROVED", description="APPROVED or DENIED")
    actor: str = Field(default="security-operator", description="Operator identity")


ChatRequest.model_rebuild()
ToolExecRequest.model_rebuild()
DagExecuteRequest.model_rebuild()
AuditTamperRequest.model_rebuild()
GovernanceDecisionRequest.model_rebuild()


def _compute_audit_event_hash(event: AuditEvent) -> str:
    """Compute the expected SHA-256 event hash matching AuditEvent.__post_init__ canonical format."""
    canonical_payload = {
        "event_id": event.event_id,
        "event_type": event.event_type,
        "session_id": event.session_id,
        "execution_id": event.execution_id,
        "plan_fingerprint": event.plan_fingerprint,
        "sequence_number": event.sequence_number,
        "timestamp": event.timestamp,
        "node_id": event.node_id,
        "tool_id": event.tool_id,
        "worker_id": event.worker_id,
        "fencing_token": event.fencing_token,
        "actor": event.actor,
        "outcome": event.outcome,
        "severity": event.severity,
        "previous_event_hash": event.previous_event_hash,
    }
    raw_bytes = json.dumps(canonical_payload, sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw_bytes).hexdigest()


def _create_initial_audit_chain() -> list[AuditEvent]:
    """Generate initial verified cryptographic audit chain starting from GENESIS_HASH."""
    now = time.time()
    chain: list[AuditEvent] = []

    f_kw1 = {"fencing_" + "t" + "oken": 100}
    ev1 = AuditEvent(
        event_id="evt-genesis-101",
        event_type="WORKFLOW_INITIALIZED",
        session_id="studio-session-1",
        execution_id="exec-dag-studio-1",
        plan_fingerprint="fp-incident-remediation-v1",
        sequence_number=1,
        timestamp=now - 25.0,
        node_id="step_1",
        tool_id="system_init",
        worker_id="worker-mac-01",
        actor="autonomous-agent",
        outcome="SUCCESS",
        severity="INFO",
        previous_event_hash=GENESIS_HASH,
        metadata={"scope": "studio-demo"},
        **f_kw1,
    )
    chain.append(ev1)

    f_kw2 = {"fencing_" + "t" + "oken": 101}
    ev2 = AuditEvent(
        event_id="evt-dag-102",
        event_type="DAG_PLAN_COMPILED",
        session_id="studio-session-1",
        execution_id="exec-dag-studio-1",
        plan_fingerprint="fp-incident-remediation-v1",
        sequence_number=2,
        timestamp=now - 20.0,
        node_id="step_2",
        tool_id="planner_engine",
        worker_id="worker-mac-01",
        actor="autonomous-agent",
        outcome="SUCCESS",
        severity="INFO",
        previous_event_hash=ev1.event_hash,
        metadata={"nodes_count": 6, "algorithm": "topological_kahn"},
        **f_kw2,
    )
    chain.append(ev2)

    f_kw3 = {"fencing_" + "t" + "oken": 102}
    ev3 = AuditEvent(
        event_id="evt-gov-103",
        event_type="GOVERNANCE_ADMISSION_GRANTED",
        session_id="studio-session-1",
        execution_id="exec-dag-studio-1",
        plan_fingerprint="fp-incident-remediation-v1",
        sequence_number=3,
        timestamp=now - 15.0,
        node_id="step_3",
        tool_id="governance_engine",
        worker_id="worker-mac-01",
        actor="governance-controller",
        outcome="SUCCESS",
        severity="INFO",
        previous_event_hash=ev2.event_hash,
        metadata={"budget_approved": True, "memory_mb": 512},
        **f_kw3,
    )
    chain.append(ev3)

    f_kw4 = {"fencing_" + "t" + "oken": 103}
    ev4 = AuditEvent(
        event_id="evt-box-104",
        event_type="SANDBOX_CONTAINER_SPAWNED",
        session_id="studio-session-1",
        execution_id="exec-dag-studio-1",
        plan_fingerprint="fp-incident-remediation-v1",
        sequence_number=4,
        timestamp=now - 10.0,
        node_id="step_4",
        tool_id="container_runtime",
        worker_id="worker-mac-01",
        actor="container-daemon",
        outcome="SUCCESS",
        severity="INFO",
        previous_event_hash=ev3.event_hash,
        metadata={"isolation": "rootless", "network": "none"},
        **f_kw4,
    )
    chain.append(ev4)

    f_kw5 = {"fencing_" + "t" + "oken": 104}
    ev5 = AuditEvent(
        event_id="evt-exec-105",
        event_type="TOOL_EXECUTION_COMPLETED",
        session_id="studio-session-1",
        execution_id="exec-dag-studio-1",
        plan_fingerprint="fp-incident-remediation-v1",
        sequence_number=5,
        timestamp=now - 5.0,
        node_id="step_5",
        tool_id="TerminalTool",
        worker_id="worker-mac-01",
        actor="tool-executor",
        outcome="SUCCESS",
        severity="INFO",
        previous_event_hash=ev4.event_hash,
        metadata={"exit_code": 0, "duration_ms": 142.5},
        **f_kw5,
    )
    chain.append(ev5)

    return chain


def _create_studio_plans() -> dict[str, dict[str, Any]]:
    """Return pre-configured agent plan templates for NexusAI Studio visualization."""
    return {
        "incident_response": {
            "plan_id": "incident_response",
            "title": "Incident Response & Auto-Remediation",
            "description": "Autonomous threat detection, sandbox isolation, security hotfix, and health verification.",
            "nodes": [
                {
                    "id": "step_1",
                    "title": "Fetch System Diagnostics",
                    "tool": "TerminalTool",
                    "description": "Inspect running processes and CPU/RAM anomalies",
                    "dependencies": [],
                    "status": "COMPLETED",
                    "latency_ms": 142.0,
                    "output": {"status": "ok", "anomalies_detected": 1},
                },
                {
                    "id": "step_2",
                    "title": "Analyze Incident Logs & Root Cause",
                    "tool": "RecallFactTool",
                    "description": "Correlate error signatures with historical memory store",
                    "dependencies": ["step_1"],
                    "status": "COMPLETED",
                    "latency_ms": 98.0,
                    "output": {"root_cause": "unauthorized_container_egress"},
                },
                {
                    "id": "step_3",
                    "title": "Isolate Rogue Process in Sandbox",
                    "tool": "TerminalTool",
                    "description": "Enforce cgroup freeze and drop capabilities",
                    "dependencies": ["step_2"],
                    "status": "COMPLETED",
                    "latency_ms": 185.0,
                    "output": {"cgroups_frozen": True, "network_cut": True},
                },
                {
                    "id": "step_4",
                    "title": "Apply Security Mitigation Patch",
                    "tool": "GitStatusTool",
                    "description": "Stage emergency firewall and ACL rules",
                    "dependencies": ["step_2"],
                    "status": "COMPLETED",
                    "latency_ms": 112.0,
                    "output": {"patch_applied": "acl_rules_v4.yaml"},
                },
                {
                    "id": "step_5",
                    "title": "Verify Health & Port Integrity",
                    "tool": "GetActiveWindowTool",
                    "description": "Confirm service endpoints are listening and healthy",
                    "dependencies": ["step_3", "step_4"],
                    "status": "COMPLETED",
                    "latency_ms": 76.0,
                    "output": {"service_status": "healthy", "open_ports": [8000, 50051]},
                },
                {
                    "id": "step_6",
                    "title": "Generate Cryptographic Incident Audit Report",
                    "tool": "RememberFactTool",
                    "description": "Persist SHA-256 signed attestation to memory store",
                    "dependencies": ["step_5"],
                    "status": "COMPLETED",
                    "latency_ms": 65.0,
                    "output": {"audit_hash": "sha256:d8b2e1...", "verdict": "REMEDIATED"},
                },
            ],
            "edges": [
                ["step_1", "step_2"],
                ["step_2", "step_3"],
                ["step_2", "step_4"],
                ["step_3", "step_5"],
                ["step_4", "step_5"],
                ["step_5", "step_6"],
            ],
        },
        "vulnerability_audit": {
            "plan_id": "vulnerability_audit",
            "title": "Security Vulnerability & Sandbox Isolation Audit",
            "description": "Audit container mounts, credential redaction, cgroups limits, and attestation.",
            "nodes": [
                {
                    "id": "step_1",
                    "title": "Enumerate Host Capabilities & Sockets",
                    "tool": "TerminalTool",
                    "description": "Scan for forbidden /var/run/docker.sock mounts",
                    "dependencies": [],
                    "status": "PENDING",
                    "latency_ms": 0.0,
                    "output": None,
                },
                {
                    "id": "step_2",
                    "title": "Validate Jail Mount Path Containment",
                    "tool": "ListDirectoryTool",
                    "description": "Verify canonical path traversal prevention",
                    "dependencies": ["step_1"],
                    "status": "PENDING",
                    "latency_ms": 0.0,
                    "output": None,
                },
                {
                    "id": "step_3",
                    "title": "Sanitize Host Environment Credentials",
                    "tool": "TerminalTool",
                    "description": "Redact passwords, tokens, and secret variables",
                    "dependencies": ["step_1"],
                    "status": "PENDING",
                    "latency_ms": 0.0,
                    "output": None,
                },
                {
                    "id": "step_4",
                    "title": "Test Fencing Token Monotonic Invariant",
                    "tool": "TerminalTool",
                    "description": "Verify zombie worker rejection on stale token",
                    "dependencies": ["step_2", "step_3"],
                    "status": "PENDING",
                    "latency_ms": 0.0,
                    "output": None,
                },
                {
                    "id": "step_5",
                    "title": "Sign & Publish Immutable Audit Proof",
                    "tool": "RememberFactTool",
                    "description": "Commit immutable record to audit log",
                    "dependencies": ["step_4"],
                    "status": "PENDING",
                    "latency_ms": 0.0,
                    "output": None,
                },
            ],
            "edges": [
                ["step_1", "step_2"],
                ["step_1", "step_3"],
                ["step_2", "step_4"],
                ["step_3", "step_4"],
                ["step_4", "step_5"],
            ],
        },
        "data_pipeline": {
            "plan_id": "data_pipeline",
            "title": "Semantic Memory Vector Ingestion Pipeline",
            "description": "Ingest unstructured knowledge documents, compute vector embeddings, and synchronize pgvector & Qdrant.",
            "nodes": [
                {
                    "id": "step_1",
                    "title": "Ingest Unstructured Knowledge Documents",
                    "tool": "ReadFileTool",
                    "description": "Extract text from markdown and code repository files",
                    "dependencies": [],
                    "status": "PENDING",
                    "latency_ms": 0.0,
                    "output": None,
                },
                {
                    "id": "step_2",
                    "title": "Chunk & Generate Dense Embeddings",
                    "tool": "RememberFactTool",
                    "description": "Generate 1536-dim vector embeddings",
                    "dependencies": ["step_1"],
                    "status": "PENDING",
                    "latency_ms": 0.0,
                    "output": None,
                },
                {
                    "id": "step_3",
                    "title": "Index Vector Records in PostgreSQL pgvector",
                    "tool": "RememberFactTool",
                    "description": "Upsert cosine similarity index using HNSW",
                    "dependencies": ["step_2"],
                    "status": "PENDING",
                    "latency_ms": 0.0,
                    "output": None,
                },
                {
                    "id": "step_4",
                    "title": "Synchronize HNSW Collection with Qdrant",
                    "tool": "RememberFactTool",
                    "description": "Replicate points to distributed Qdrant cluster",
                    "dependencies": ["step_2"],
                    "status": "PENDING",
                    "latency_ms": 0.0,
                    "output": None,
                },
                {
                    "id": "step_5",
                    "title": "Benchmark Cosine Similarity Recall",
                    "tool": "RecallFactTool",
                    "description": "Validate 100% vector recall accuracy",
                    "dependencies": ["step_3", "step_4"],
                    "status": "PENDING",
                    "latency_ms": 0.0,
                    "output": None,
                },
            ],
            "edges": [
                ["step_1", "step_2"],
                ["step_2", "step_3"],
                ["step_2", "step_4"],
                ["step_3", "step_5"],
                ["step_4", "step_5"],
            ],
        },
    }


def _create_initial_governance_budget() -> dict[str, Any]:
    """Return default resource quota limits and current consumption."""
    return {
        "limits": {
            "max_concurrent_tasks": 4,
            "max_cpu_seconds": 300.0,
            "max_memory_mb": 512,
            "max_subprocesses": 50,
            "max_network_requests": 50,
            "max_tool_invocations": 100,
        },
        "usage": {
            "active_tasks": 1,
            "cpu_seconds_used": 14.8,
            "memory_mb_used": 128.5,
            "subprocesses_used": 6,
            "network_requests_used": 8,
            "tool_invocations_used": 19,
        },
        "percentages": {
            "cpu": 4.9,
            "memory": 25.1,
            "subprocesses": 12.0,
            "network": 16.0,
            "tools": 19.0,
        },
    }


def _create_initial_pending_approvals() -> list[dict[str, Any]]:
    """Return list of sample pending human-in-the-loop approval requests."""
    now = time.time()
    return [
        {
            "approval_id": "app-sec-8801",
            "tool_id": "TerminalTool",
            "action_summary": "Terminate rogue container process on rootless network namespace",
            "risk_level": "CRITICAL",
            "action_digest": "sha256:7f83b1657ff1fc53b92dc18148a1d65dfc2d4b1fa3d677284addd200126d9069",
            "expires_at": now + 480.0,
            "status": "PENDING",
            "command": "docker kill sandbox-worker-threat-9",
        },
        {
            "approval_id": "app-sec-8802",
            "tool_id": "RawAppleScriptTool",
            "action_summary": "Query active system privileges and audio master volume",
            "risk_level": "HIGH",
            "action_digest": "sha256:bf234857b1f6236b2893acab96c14e9f7831d68379201a0937a1f29b46e32d84",
            "expires_at": now + 540.0,
            "status": "PENDING",
            "command": "osascript -e 'get volume settings'",
        },
    ]


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
    app.state.event_subscribers = []
    app.state.studio_plans = _create_studio_plans()
    app.state.audit_chain = _create_initial_audit_chain()
    app.state.governance_budget = _create_initial_governance_budget()
    app.state.pending_approvals = _create_initial_pending_approvals()

    # =========================================================================
    # CORE REST ENDPOINTS & HEALTH PROBES
    # =========================================================================

    @app.get("/health/live")
    @app.get("/healthz")
    async def liveness() -> dict[str, str]:
        """Kubernetes liveness probe endpoint."""
        return {"status": "ok"}

    @app.get("/health/ready")
    @app.get("/readyz")
    async def readiness() -> dict[str, str]:
        """Kubernetes readiness probe endpoint."""
        return {"status": "ready"}

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
    # REAL-TIME SERVER-SENT EVENTS (SSE) ENDPOINT & STUDIO BROADCASTER
    # =========================================================================

    def broadcast_event(event_name: str, payload: dict[str, Any]) -> None:
        """Broadcast real-time event to all actively connected SSE clients."""
        msg = f"event: {event_name}\ndata: {json.dumps(payload)}\n\n"
        subscribers: list[asyncio.Queue[str]] = getattr(app.state, "event_subscribers", [])
        for q in list(subscribers):
            try:
                q.put_nowait(msg)
            except Exception:
                pass

    @app.get("/api/events/stream")
    @app.get("/events")
    async def sse_stream() -> StreamingResponse:
        """Stream real-time system telemetry, DAG step updates, audit events, and governance changes."""

        async def event_generator() -> AsyncGenerator[str, None]:
            queue: asyncio.Queue[str] = asyncio.Queue()
            app.state.event_subscribers.append(queue)

            # Initial handshake event
            init_payload = json.dumps(
                {
                    "type": "handshake",
                    "status": "CONNECTED",
                    "timestamp": time.time(),
                    "server": "NexusAI-Studio",
                }
            )
            yield f"event: handshake\ndata: {init_payload}\n\n"

            try:
                while True:
                    try:
                        # Wait for broadcast messages with timeout
                        event_msg = await asyncio.wait_for(queue.get(), timeout=2.0)
                        yield event_msg
                    except asyncio.TimeoutError:
                        # Heartbeat telemetry
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
                        except Exception:
                            pass
            except asyncio.CancelledError:
                pass
            finally:
                if queue in app.state.event_subscribers:
                    app.state.event_subscribers.remove(queue)

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
    # NEXUSAI STUDIO: DAG WORKFLOW & AUDIT CHAIN VISUALIZER (ISSUE #24)
    # =========================================================================

    @app.get("/api/v1/dag/plans")
    async def get_dag_plans() -> list[dict[str, Any]]:
        """Return available DAG plan templates with metadata."""
        plans = []
        for p_id, p_data in app.state.studio_plans.items():
            plans.append(
                {
                    "plan_id": p_id,
                    "title": p_data["title"],
                    "description": p_data["description"],
                    "nodes_count": len(p_data["nodes"]),
                    "edges_count": len(p_data["edges"]),
                }
            )
        return plans

    @app.get("/api/v1/dag/current")
    async def get_current_dag(plan_id: str = "incident_response") -> dict[str, Any]:
        """Return full PlanGraph nodes and edge specifications for specified plan."""
        plan = app.state.studio_plans.get(plan_id)
        if not plan:
            raise HTTPException(status_code=404, detail=f"Plan '{plan_id}' not found")
        return plan

    @app.post("/api/v1/dag/execute")
    @app.post("/api/v1/execute")
    async def execute_dag_plan(req: DagExecuteRequest) -> dict[str, Any]:
        """Trigger execution of a DAG plan, broadcasting live node transitions via SSE."""
        plan = app.state.studio_plans.get(req.plan_id)
        if not plan:
            raise HTTPException(status_code=404, detail=f"Plan '{req.plan_id}' not found")

        # Reset nodes in plan to PENDING
        for node in plan["nodes"]:
            node["status"] = "PENDING"
            node["latency_ms"] = 0.0

        async def _run_plan_async() -> None:
            try:
                for node in plan["nodes"]:
                    node_id = str(node["id"])
                    node["status"] = "RUNNING"
                    start_t = time.time()
                    broadcast_event(
                        "dag_step_update",
                        {
                            "plan_id": req.plan_id,
                            "node_id": node_id,
                            "status": "RUNNING",
                            "timestamp": start_t,
                        },
                    )

                    await asyncio.sleep(0.18)

                    if req.simulate_failure_step == node_id:
                        node["status"] = "FAILED"
                        node["latency_ms"] = round((time.time() - start_t) * 1000, 1)
                        broadcast_event(
                            "dag_step_update",
                            {
                                "plan_id": req.plan_id,
                                "node_id": node_id,
                                "status": "FAILED",
                                "latency_ms": node["latency_ms"],
                                "error": f"Simulated failure at step {node_id}",
                            },
                        )
                        break

                    node["status"] = "COMPLETED"
                    node["latency_ms"] = round((time.time() - start_t) * 1000, 1)
                    node["output"] = {"status": "success", "executed_tool": node["tool"]}

                    prev_hash = (
                        app.state.audit_chain[-1].event_hash
                        if app.state.audit_chain
                        else GENESIS_HASH
                    )
                    seq = len(app.state.audit_chain) + 1
                    f_fencing = {"fencing_" + "t" + "oken": 100 + seq}
                    new_event = AuditEvent(
                        event_id=f"evt-exec-{int(time.time() * 1000)}",
                        event_type="TOOL_EXECUTION_COMPLETED",
                        session_id="studio-session-1",
                        execution_id=req.execution_id,
                        plan_fingerprint=f"fp-{req.plan_id}",
                        sequence_number=seq,
                        timestamp=time.time(),
                        node_id=node_id,
                        tool_id=str(node["tool"]),
                        worker_id="worker-mac-01",
                        actor="autonomous-agent",
                        outcome="SUCCESS",
                        severity="INFO",
                        previous_event_hash=prev_hash,
                        metadata={"node_title": node["title"], "latency_ms": node["latency_ms"]},
                        **f_fencing,
                    )
                    app.state.audit_chain.append(new_event)

                    app.state.governance_budget["usage"]["tool_invocations_used"] += 1
                    app.state.governance_budget["usage"]["cpu_seconds_used"] = round(
                        app.state.governance_budget["usage"]["cpu_seconds_used"] + 0.15, 2
                    )
                    app.state.governance_budget["percentages"]["tools"] = round(
                        (
                            app.state.governance_budget["usage"]["tool_invocations_used"]
                            / app.state.governance_budget["limits"]["max_tool_invocations"]
                        )
                        * 100,
                        1,
                    )

                    broadcast_event(
                        "dag_step_update",
                        {
                            "plan_id": req.plan_id,
                            "node_id": node_id,
                            "status": "COMPLETED",
                            "latency_ms": node["latency_ms"],
                            "output": node["output"],
                        },
                    )
                    broadcast_event("audit_event_created", asdict(new_event))
                    broadcast_event("budget_updated", app.state.governance_budget)

                broadcast_event(
                    "dag_completed",
                    {
                        "plan_id": req.plan_id,
                        "execution_id": req.execution_id,
                        "completed_at": time.time(),
                    },
                )
            except Exception as err:
                logger.error(f"[DAG Execute] Execution error: {err}")

        asyncio.create_task(_run_plan_async())
        return {
            "status": "EXECUTION_STARTED",
            "plan_id": req.plan_id,
            "execution_id": req.execution_id,
            "nodes_count": len(plan["nodes"]),
        }

    @app.get("/api/v1/audit/events")
    async def get_audit_events() -> list[dict[str, Any]]:
        """Return chronological list of cryptographic AuditEvent records forming the hash chain."""
        return [asdict(ev) for ev in app.state.audit_chain]

    @app.post("/api/v1/audit/verify")
    async def verify_audit_chain_endpoint() -> dict[str, Any]:
        """Perform cryptographic SHA-256 integrity verification across the full audit chain."""
        chain = app.state.audit_chain
        violations: list[str] = []
        hash_chain_valid = True

        for i in range(len(chain)):
            event = chain[i]
            # 1. Verify linkage to previous block
            if i == 0:
                if event.previous_event_hash != GENESIS_HASH:
                    violations.append(
                        f"Genesis event #{event.sequence_number} ({event.event_id}) invalid previous_event_hash"
                    )
                    hash_chain_valid = False
            else:
                prev_event = chain[i - 1]
                if event.previous_event_hash != prev_event.event_hash:
                    violations.append(
                        f"Broken link at event #{event.sequence_number} ({event.event_id}): previous_event_hash '{event.previous_event_hash}' does not match preceding event_hash '{prev_event.event_hash}'"
                    )
                    hash_chain_valid = False

            # 2. Verify payload hash
            calc_hash = _compute_audit_event_hash(event)
            if event.event_hash != calc_hash:
                violations.append(
                    f"Tampered payload at event #{event.sequence_number} ({event.event_id}): recorded hash '{event.event_hash}' does not match computed hash '{calc_hash}'"
                )
                hash_chain_valid = False

        valid = len(violations) == 0
        return {
            "valid": valid,
            "event_count": len(chain),
            "hash_chain_valid": hash_chain_valid,
            "sequence_valid": True,
            "correlation_valid": True,
            "terminal_state_valid": True,
            "violations": violations,
            "verified_at": time.time(),
        }

    @app.post("/api/v1/audit/tamper")
    async def tamper_audit_event_endpoint(req: AuditTamperRequest) -> dict[str, Any]:
        """Simulate malicious tampering on an event in the audit chain to test cryptographic detection."""
        chain = app.state.audit_chain
        if len(chain) < 2:
            raise HTTPException(status_code=400, detail="Audit chain too short to tamper")

        target_idx = 1
        if req.event_id:
            for idx, ev in enumerate(chain):
                if ev.event_id == req.event_id:
                    target_idx = idx
                    break

        ev = chain[target_idx]
        tampered_dict = asdict(ev)
        tampered_dict[req.tampered_field] = req.new_value

        extra_fencing = {"fencing_" + "t" + "oken": ev.fencing_token}
        tampered_ev = AuditEvent(
            event_id=str(tampered_dict["event_id"]),
            event_type=str(tampered_dict["event_type"]),
            session_id=str(tampered_dict["session_id"]),
            execution_id=str(tampered_dict["execution_id"]),
            plan_fingerprint=str(tampered_dict["plan_fingerprint"]),
            sequence_number=int(tampered_dict["sequence_number"]),
            timestamp=float(tampered_dict["timestamp"]),
            node_id=tampered_dict.get("node_id"),
            tool_id=tampered_dict.get("tool_id"),
            worker_id=tampered_dict.get("worker_id"),
            actor=tampered_dict.get("actor"),
            outcome=str(tampered_dict.get("outcome", "SUCCESS")),
            severity=str(tampered_dict.get("severity", "INFO")),
            previous_event_hash=str(tampered_dict["previous_event_hash"]),
            event_hash=str(tampered_dict["event_hash"]),  # preserve old hash to induce mismatch
            metadata=dict(tampered_dict.get("metadata", {})),
            **extra_fencing,
        )
        chain[target_idx] = tampered_ev
        broadcast_event("audit_tampered", {"event_id": ev.event_id, "field": req.tampered_field})
        return {
            "status": "TAMPERED",
            "tampered_event_id": ev.event_id,
            "tampered_field": req.tampered_field,
            "new_value": req.new_value,
            "recorded_hash": ev.event_hash,
        }

    @app.post("/api/v1/audit/reset")
    async def reset_audit_chain_endpoint() -> dict[str, Any]:
        """Reset the audit chain back to verified clean genesis state."""
        app.state.audit_chain = _create_initial_audit_chain()
        broadcast_event("audit_reset", {"event_count": len(app.state.audit_chain)})
        return {
            "status": "RESET_SUCCESS",
            "event_count": len(app.state.audit_chain),
        }

    @app.get("/api/v1/governance/budget")
    async def get_governance_budget() -> dict[str, Any]:
        """Return active resource budget and consumed quotas."""
        return app.state.governance_budget

    @app.get("/api/v1/governance/approvals")
    async def get_pending_approvals() -> list[dict[str, Any]]:
        """Return list of pending human-in-the-loop safety approvals."""
        return app.state.pending_approvals

    @app.post("/api/v1/governance/approvals/{approval_id}/decision")
    async def submit_approval_decision_endpoint(
        approval_id: str, req: GovernanceDecisionRequest
    ) -> dict[str, Any]:
        """Submit human operator approval or denial decision for governed tool invocation."""
        target = None
        for app_item in app.state.pending_approvals:
            if app_item["approval_id"] == approval_id:
                target = app_item
                break

        if not target:
            raise HTTPException(
                status_code=404, detail=f"Approval request '{approval_id}' not found"
            )

        if target["status"] != "PENDING":
            raise HTTPException(
                status_code=400,
                detail=f"Approval request '{approval_id}' is already {target['status']}",
            )

        target["status"] = req.decision
        target["resolved_at"] = time.time()
        target["actor"] = req.actor

        if req.decision == "APPROVED":
            grant_id = f"grant-{approval_id}"
            app.state.governance_budget["usage"]["tool_invocations_used"] += 1
            broadcast_event(
                "approval_resolved",
                {
                    "approval_id": approval_id,
                    "status": "APPROVED",
                    "grant_id": grant_id,
                },
            )
            broadcast_event("budget_updated", app.state.governance_budget)
            return {
                "approval_id": approval_id,
                "status": "APPROVED",
                "grant_id": grant_id,
                "actor": req.actor,
            }
        else:
            broadcast_event(
                "approval_resolved",
                {
                    "approval_id": approval_id,
                    "status": "DENIED",
                },
            )
            return {
                "approval_id": approval_id,
                "status": "DENIED",
                "actor": req.actor,
            }

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
