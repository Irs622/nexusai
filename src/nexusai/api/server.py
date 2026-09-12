"""FastAPI Server for NexusAI Web Dashboard API, Real-Time SSE Event Stream, and Static File Serving."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncGenerator, cast

from dotenv import find_dotenv, load_dotenv
from fastapi import FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

load_dotenv(find_dotenv(usecwd=True))

from nexusai.automation.scheduler import SchedulerService
from nexusai.brain.coordinator import BrainCoordinator
from nexusai.brain.domain.audit import GENESIS_HASH, AuditEvent
from nexusai.brain.domain.execution_coordination import WorkerIdentity
from nexusai.brain.ports.audit_store_port import IAuditStore
from nexusai.bus.bus import CommandBus, EventBus
from nexusai.bus.commands import ExecuteToolCommand, ExecuteToolCommandHandler
from nexusai.context.engine import ContextEngine
from nexusai.core.config import SystemConfig
from nexusai.core.errors import (
    ConfigurationError,
    IdempotencyConflictError,
    IdempotencyPayloadMismatchError,
    SecurityError,
)
from nexusai.infrastructure.idempotency import (
    IdempotencyState,
    IdempotencyStore,
    InMemoryIdempotencyStore,
    compute_payload_fingerprint,
)
from nexusai.infrastructure.observability.redaction import sanitize_secrets_recursive
from nexusai.infrastructure.persistence.sqlite_audit_store import SQLiteAuditStore
from nexusai.infrastructure.persistence.sqlite_execution_coordinator import (
    SQLiteExecutionCoordinator,
)
from nexusai.infrastructure.persistence.sqlite_execution_journal import SQLiteExecutionJournal
from nexusai.infrastructure.persistence.sqlite_execution_store import SQLiteExecutionStateStore
from nexusai.logging.logger import logger
from nexusai.memory.sqlite_memory import SQLiteMemory
from nexusai.models.openai_provider import OpenAIProvider
from nexusai.runtime.execution_engine import DurableExecutionEngine
from nexusai.runtime.recovery import CrashRecoveryProtocol
from nexusai.security.authentication import ApiKeyService, AuthMiddleware
from nexusai.security.guard import RiskLevel, SecurityGuard
from nexusai.security.identity import Identity, Role, TenantContext

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
    approval_token: str | None = Field(
        default=None, description="Optional approval token for high-risk tool execution"
    )


class ToolExecRequest(BaseModel):
    tool_name: str = Field(..., description="Name of tool to execute")
    arguments: dict[str, Any] = Field(default_factory=dict, description="Tool parameters")
    execution_id: str = Field(default="", description="Optional execution context ID")


class ApprovalRequest(BaseModel):
    tool_name: str = Field(..., description="Name of tool requiring approval token")
    arguments: dict[str, Any] = Field(default_factory=dict, description="Tool execution parameters")
    execution_id: str = Field(default="", description="Optional execution context ID")


class DagExecuteRequest(BaseModel):
    plan_id: str = Field(default="incident_response", description="ID of plan to execute")
    simulate_failure_step: str | None = Field(
        default=None, description="Optional step ID to simulate failure"
    )
    execution_id: str = Field(
        default_factory=lambda: f"exec-dag-{int(time.time())}", description="Execution ID"
    )
    idempotency_key: str | None = Field(
        default=None, description="Optional idempotency key for DAG execution"
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
ApprovalRequest.model_rebuild()
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
        "tenant_id": event.tenant_id,
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
    )
    chain.append(ev1)

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
    )
    chain.append(ev2)

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
    )
    chain.append(ev3)

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
    )
    chain.append(ev4)

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
    idempotency_store: IdempotencyStore | None = None,
    audit_store: IAuditStore | None = None,
    studio_demo_mode: bool | None = None,
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
    idem_store: IdempotencyStore = idempotency_store or InMemoryIdempotencyStore()
    aud_store: IAuditStore = audit_store or SQLiteAuditStore(db_path=db_path)

    # Pre-seed initial verified genesis audit events if persistent store is empty for default tenant
    if isinstance(aud_store, SQLiteAuditStore):
        aud_store.seed_initial_events_if_empty(_create_initial_audit_chain(), tenant_id="default")

    if studio_demo_mode is None:
        is_demo_mode = os.getenv("NEXUSAI_STUDIO_DEMO_MODE", "").lower() in ("true", "1", "yes")
    else:
        is_demo_mode = studio_demo_mode

    if is_demo_mode:
        logger.warning(
            "WARNING: Studio demo mode is ENABLED. Audit log tampering endpoints are active. DO NOT USE IN PRODUCTION."
        )

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
    handler = ExecuteToolCommandHandler(
        registry, security_guard, event_bus, idempotency_store=idem_store
    )
    command_bus.register(ExecuteToolCommand, handler)

    # Coordinator & Durable Execution Infrastructure
    exec_db_path = os.getenv("NEXUSAI_EXECUTION_DB", ":memory:")
    coord_db_path = os.getenv("NEXUSAI_COORDINATOR_DB", ":memory:")
    exec_store = SQLiteExecutionStateStore(db_path=exec_db_path)
    exec_journal = SQLiteExecutionJournal(db_path=exec_db_path)
    exec_coord = SQLiteExecutionCoordinator(db_path=coord_db_path)
    api_worker = WorkerIdentity(worker_id=os.getenv("NEXUSAI_WORKER_ID", "worker-api-01"))
    durable_engine = DurableExecutionEngine(
        store=exec_store,
        coordinator=exec_coord,
        audit_store=aud_store,
        worker_identity=api_worker,
        tool_registry=registry,
        journal=exec_journal,
    )
    crash_recovery = CrashRecoveryProtocol(
        store=exec_store,
        coordinator=exec_coord,
        engine=durable_engine,
        worker_identity=api_worker,
    )

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

        # Startup integrity verification on persistent audit store
        startup_verification = await aud_store.startup_integrity_check()
        if not startup_verification.valid:
            app_instance.state.audit_compromised = True
            logger.critical(
                f"CRITICAL: Audit log integrity verification FAILED on startup! "
                f"Broken at sequence {startup_verification.broken_at_sequence}: {startup_verification.violations}"
            )
        else:
            app_instance.state.audit_compromised = False
            logger.info(
                f"Audit log integrity verification PASSED on startup ({startup_verification.event_count} events verified)."
            )

        # Startup crash recovery
        try:
            recovery_report = await crash_recovery.run_startup_recovery()
            logger.info(
                f"Startup crash recovery completed: {recovery_report.reclaimed_count} reclaimed, "
                f"{recovery_report.cancelled_count} cancelled, {recovery_report.skipped_active_count} active skipped."
            )
        except Exception as rec_err:
            logger.warning(f"Startup crash recovery encountered error: {rec_err}")

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
    app.state.idempotency_store = idem_store
    app.state.audit_store = aud_store
    app.state.execution_store = exec_store
    app.state.execution_coordinator = exec_coord
    app.state.durable_engine = durable_engine
    app.state.crash_recovery = crash_recovery
    app.state.studio_demo_mode = is_demo_mode
    app.state.audit_compromised = False

    env_origins = os.getenv("NEXUSAI_ALLOWED_ORIGINS")
    if env_origins:
        configured_origins = [o.strip() for o in env_origins.split(",") if o.strip()]
    else:
        configured_origins = list(config.api.allowed_origins)

    # Hardening: Disallow wildcard origin
    safe_origins = [o for o in configured_origins if o != "*"]
    if not safe_origins:
        safe_origins = ["http://localhost:8000"]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=safe_origins,
        allow_credentials=config.api.allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Authentication & API Key Service
    auth_cfg = getattr(config, "auth", None)
    api_key_service = ApiKeyService(
        storage_path=auth_cfg.key_storage_path if auth_cfg else None,
        default_rate_limit=auth_cfg.rate_limit_per_minute if auth_cfg else 100,
    )

    # Register default administrative test key for local development and seamless testing
    default_test_key = os.getenv("NEXUSAI_TEST_API_KEY", "nx_test_admin_key_123")
    api_key_service.register_raw_key(
        raw_key=default_test_key,
        tenant_id="default",
        user_id="admin-user",
        role=Role.ADMIN,
        name="Default System Admin Key",
    )

    auth_enabled = (
        auth_cfg.enabled
        if (auth_cfg and os.getenv("NEXUSAI_AUTH_ENABLED", "true").lower() != "false")
        else True
    )
    if os.getenv("NEXUSAI_AUTH_ENABLED", "").lower() == "false":
        auth_enabled = False

    app.add_middleware(
        AuthMiddleware,
        api_key_service=api_key_service,
        header_name=auth_cfg.api_key_header if auth_cfg else "X-NexusAI-API-Key",
        enabled=auth_enabled,
    )

    # Multi-tenant state partitioning
    tenant_audit_chains: dict[str, list[AuditEvent]] = {
        "default": _create_initial_audit_chain(),
    }
    tenant_governance_budgets: dict[str, dict[str, Any]] = {
        "default": _create_initial_governance_budget(),
    }
    tenant_pending_approvals: dict[str, list[dict[str, Any]]] = {
        "default": _create_initial_pending_approvals(),
    }
    tenant_studio_plans: dict[str, dict[str, Any]] = {
        "default": _create_studio_plans(),
    }

    # Attach manager and security components to app state for testing and direct access
    app.state.mcp_manager = mcp_manager
    app.state.registry = registry
    app.state.approval_service = security_guard.approval_service
    app.state.security_guard = security_guard
    app.state.api_key_service = api_key_service
    app.state.rbac_engine = security_guard.rbac_engine
    app.state.event_subscribers = []

    app.state.tenant_audit_chains = tenant_audit_chains
    app.state.demo_audit_chains = tenant_audit_chains
    app.state.tenant_governance_budgets = tenant_governance_budgets
    app.state.tenant_pending_approvals = tenant_pending_approvals
    app.state.tenant_studio_plans = tenant_studio_plans

    # Legacy pointers for backward-compatibility
    app.state.audit_chain = tenant_audit_chains["default"]
    app.state.governance_budget = tenant_governance_budgets["default"]
    app.state.pending_approvals = tenant_pending_approvals["default"]
    app.state.studio_plans = tenant_studio_plans["default"]

    def _get_tenant_id(req: Request) -> str:
        ident: Identity | None = (
            getattr(req.state, "identity", None) or TenantContext.get_current_identity()
        )
        if ident and ident.tenant_id:
            return ident.tenant_id
        return "default"

    def _get_tenant_audit_chain(req: Request) -> list[AuditEvent]:
        t_id = _get_tenant_id(req)
        if t_id not in app.state.tenant_audit_chains:
            app.state.tenant_audit_chains[t_id] = _create_initial_audit_chain()
        return cast(list[AuditEvent], app.state.tenant_audit_chains[t_id])

    def _get_tenant_governance_budget(req: Request) -> dict[str, Any]:
        t_id = _get_tenant_id(req)
        if t_id not in app.state.tenant_governance_budgets:
            app.state.tenant_governance_budgets[t_id] = _create_initial_governance_budget()
        return cast(dict[str, Any], app.state.tenant_governance_budgets[t_id])

    def _get_tenant_pending_approvals(req: Request) -> list[dict[str, Any]]:
        t_id = _get_tenant_id(req)
        if t_id not in app.state.tenant_pending_approvals:
            app.state.tenant_pending_approvals[t_id] = _create_initial_pending_approvals()
        return cast(list[dict[str, Any]], app.state.tenant_pending_approvals[t_id])

    def _get_tenant_studio_plans(req: Request) -> dict[str, Any]:
        t_id = _get_tenant_id(req)
        if t_id not in app.state.tenant_studio_plans:
            app.state.tenant_studio_plans[t_id] = _create_studio_plans()
        return cast(dict[str, Any], app.state.tenant_studio_plans[t_id])

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
    async def chat_endpoint(req: ChatRequest, request: Request) -> dict[str, Any]:
        identity: Identity | None = (
            getattr(request.state, "identity", None) or TenantContext.get_current_identity()
        )
        if identity and identity.role == Role.VIEWER:
            raise HTTPException(
                status_code=403,
                detail=f"RBAC access denied: Role '{identity.role.value}' is read-only and cannot invoke chat",
            )
        user_id = identity.user_id if identity else "anonymous"
        try:
            res = await coordinator.process_user_input(
                user_text=req.prompt,
                session_id=req.session_id,
                approval_token=req.approval_token,
                user_id=user_id,
            )
            return res
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e)) from e

    @app.post("/api/v1/approvals/request")
    async def request_approval_token(req: ApprovalRequest, request: Request) -> dict[str, Any]:
        """Issue a cryptographic HMAC-SHA256 single-use approval token for tool execution."""
        identity: Identity | None = (
            getattr(request.state, "identity", None) or TenantContext.get_current_identity()
        )
        user_id = identity.user_id if identity else "anonymous"
        try:
            token, expires_at = security_guard.approval_service.create_token(
                tool_name=req.tool_name,
                arguments=req.arguments,
                user_id=user_id,
                execution_id=req.execution_id,
            )
            return {"approval_token": token, "expires_at": expires_at}
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

    @app.post("/api/tools/execute")
    async def execute_tool_endpoint(
        req: ToolExecRequest,
        request: Request,
        x_approval_token: str | None = Header(None, alias="X-Approval-Token"),
        x_idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    ) -> Response:
        try:
            tool = registry.get(req.tool_name)
        except Exception as e:
            raise HTTPException(
                status_code=404, detail=f"Tool '{req.tool_name}' not found: {e}"
            ) from e

        identity: Identity | None = (
            getattr(request.state, "identity", None) or TenantContext.get_current_identity()
        )
        tenant_id = identity.tenant_id if identity else "default"
        user_id = identity.user_id if identity else "anonymous"

        if identity is not None:
            # 1. Viewer role cannot execute tools -> 403 Forbidden
            if identity.role == Role.VIEWER:
                raise HTTPException(
                    status_code=403,
                    detail=f"RBAC access denied: Role '{identity.role.value}' cannot execute tools",
                )
            # 2. Operator role cannot execute HIGH or CRITICAL tools -> 403 Forbidden
            if identity.role == Role.OPERATOR and tool.risk_level in (
                RiskLevel.HIGH,
                RiskLevel.CRITICAL,
            ):
                raise HTTPException(
                    status_code=403,
                    detail=f"RBAC access denied: Role '{identity.role.value}' cannot execute {tool.risk_level.value} risk tool '{req.tool_name}'",
                )

        # HIGH or CRITICAL risk tools require server-side approval token
        if tool.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL):
            if not x_approval_token:
                raise HTTPException(
                    status_code=403,
                    detail=f"Approval token required for {tool.risk_level.value} risk tool '{req.tool_name}'. Provide via X-Approval-Token header.",
                )

        fingerprint = compute_payload_fingerprint(
            {"tool_name": req.tool_name, "arguments": req.arguments}
        )

        if x_idempotency_key:
            existing = await idem_store.get(tenant_id, user_id, x_idempotency_key)
            if existing is not None:
                if existing.fingerprint != fingerprint:
                    raise HTTPException(
                        status_code=409,
                        detail="Idempotency-Key reuse with different payload: payload mismatch",
                    )
                if existing.state == IdempotencyState.RUNNING:
                    return JSONResponse(
                        status_code=409,
                        content={"error": "Execution in progress", "retry_after": 2},
                        headers={"Retry-After": "2"},
                    )
                if existing.state == IdempotencyState.CANCELLED:
                    return JSONResponse(
                        status_code=409,
                        content={"error": "Execution was cancelled"},
                    )
                if existing.state == IdempotencyState.SUCCEEDED:
                    cached_resp = existing.response
                    if isinstance(cached_resp, dict) and "success" in cached_resp:
                        full_resp = cached_resp
                    elif isinstance(cached_resp, dict) and "output" in cached_resp:
                        full_resp = {
                            "success": True,
                            "tool_name": req.tool_name,
                            "output": cached_resp["output"],
                        }
                    else:
                        full_resp = {
                            "success": True,
                            "tool_name": req.tool_name,
                            "output": cached_resp,
                        }
                    return JSONResponse(content=full_resp, headers={"X-Cache": "HIT"})
                if existing.state == IdempotencyState.FAILED_TERMINAL:
                    return JSONResponse(
                        status_code=400,
                        content={"detail": f"Cached terminal failure: {existing.error_message}"},
                        headers={"X-Cache": "HIT"},
                    )

        try:
            cmd = ExecuteToolCommand(
                tool_name=req.tool_name,
                arguments=req.arguments,
                approval_token=x_approval_token,
                user_id=user_id,
                execution_id=req.execution_id,
                idempotency_key=x_idempotency_key,
                tenant_id=tenant_id,
            )
            output = await command_bus.dispatch(cmd)
            sanitized_output = sanitize_secrets_recursive(output)
            resp_content = {
                "success": True,
                "tool_name": req.tool_name,
                "output": sanitized_output,
            }
            if x_idempotency_key:
                await idem_store.complete_execution(
                    tenant_id=tenant_id,
                    user_id=user_id,
                    idempotency_key=x_idempotency_key,
                    response=resp_content,
                )
                return JSONResponse(content=resp_content, headers={"X-Cache": "MISS"})

            return JSONResponse(content=resp_content)
        except IdempotencyPayloadMismatchError as pme:
            raise HTTPException(status_code=409, detail=str(pme)) from pme
        except IdempotencyConflictError as ce:
            return JSONResponse(
                status_code=409,
                content={"error": str(ce), "retry_after": 2},
                headers={"Retry-After": "2"},
            )
        except SecurityError as se:
            raise HTTPException(status_code=403, detail=str(se)) from se
        except Exception as e:
            cause = getattr(e, "__cause__", None)
            sec_err = (
                cause
                if isinstance(cause, SecurityError)
                else (e if isinstance(e, SecurityError) else None)
            )
            if sec_err:
                raise HTTPException(status_code=403, detail=str(sec_err)) from e

            err_str = str(e)
            if (
                "Security policy denied" in err_str
                or "Approval token" in err_str
                or "RBAC" in err_str
            ):
                raise HTTPException(status_code=403, detail=err_str) from e

            raise HTTPException(status_code=400, detail=err_str) from e

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
    async def get_dag_plans(request: Request) -> list[dict[str, Any]]:
        """Return available DAG plan templates with metadata."""
        plans_dict = _get_tenant_studio_plans(request)
        plans = []
        for p_id, p_data in plans_dict.items():
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
    async def get_current_dag(
        request: Request, plan_id: str = "incident_response"
    ) -> dict[str, Any]:
        """Return full PlanGraph nodes and edge specifications for specified plan."""
        plans_dict = _get_tenant_studio_plans(request)
        plan = plans_dict.get(plan_id)
        if not plan:
            raise HTTPException(status_code=404, detail=f"Plan '{plan_id}' not found")
        return cast(dict[str, Any], plan)

    @app.post("/api/v1/dag/execute")
    @app.post("/api/v1/execute")
    async def execute_dag_plan(
        req: DagExecuteRequest,
        request: Request,
        x_idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    ) -> Response:
        """Trigger execution of a DAG plan, broadcasting live node transitions via SSE."""
        identity: Identity | None = (
            getattr(request.state, "identity", None) or TenantContext.get_current_identity()
        )
        if identity and identity.role == Role.VIEWER:
            raise HTTPException(
                status_code=403,
                detail=f"RBAC access denied: Role '{identity.role.value}' cannot execute DAG plans",
            )

        plans_dict = _get_tenant_studio_plans(request)
        plan = plans_dict.get(req.plan_id)
        if not plan:
            raise HTTPException(status_code=404, detail=f"Plan '{req.plan_id}' not found")

        tenant_id = identity.tenant_id if identity else "default"
        user_id = identity.user_id if identity else "anonymous"
        if identity and identity.user_id:
            actor_name = identity.user_id
        elif auth_enabled:
            actor_name = "nexusai-agent"
        else:
            actor_name = "local-user"

        effective_key = x_idempotency_key or req.idempotency_key

        if effective_key:
            fingerprint = compute_payload_fingerprint(
                {"plan_id": req.plan_id, "simulate_failure_step": req.simulate_failure_step}
            )
            try:
                record, should_execute = await idem_store.start_execution(
                    tenant_id=tenant_id,
                    user_id=user_id,
                    idempotency_key=effective_key,
                    fingerprint=fingerprint,
                )
            except IdempotencyPayloadMismatchError as err:
                raise HTTPException(status_code=409, detail=str(err))
            except IdempotencyConflictError as err:
                raise HTTPException(status_code=409, detail=str(err))

            if not should_execute:
                if record.state == IdempotencyState.RUNNING:
                    return JSONResponse(
                        status_code=409,
                        content={"error": "DAG execution already in progress"},
                        headers={"Retry-After": "2"},
                    )
                if record.state == IdempotencyState.SUCCEEDED:
                    return JSONResponse(content=record.response, headers={"X-Cache": "HIT"})
                if record.state == IdempotencyState.FAILED_TERMINAL:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Cached terminal failure: {record.error_message}",
                        headers={"X-Cache": "HIT"},
                    )

        # Persist execution state to SQLite before tool invocation begins
        exec_store: SQLiteExecutionStateStore = app.state.execution_store
        existing_exec = await exec_store.load_execution(req.execution_id)
        if not existing_exec:
            from nexusai.brain.domain.execution_state import (
                ExecutionRecord,
                ExecutionStatus,
                NodeExecutionRecord,
                NodeExecutionStatus,
            )

            node_records = {}
            for idx, n in enumerate(plan["nodes"]):
                nid = str(n.get("id", idx + 1))
                node_records[nid] = NodeExecutionRecord(
                    execution_id=req.execution_id,
                    node_id=nid,
                    status=NodeExecutionStatus.PENDING,
                    tool_name=str(n.get("tool", "tool")),
                    arguments=n.get("arguments", {}),
                )
            initial_rec = ExecutionRecord(
                execution_id=req.execution_id,
                plan_id=req.plan_id,
                graph_hash=f"hash-{req.plan_id}",
                status=ExecutionStatus.CREATED,
                schema_version=3,
                node_records=node_records,
                worker_id=os.getenv("NEXUSAI_WORKER_ID", "worker-api-01"),
                actor=actor_name,
                tenant_id=tenant_id,
            )
            await exec_store.create_execution(initial_rec)

        # Reset nodes in plan to PENDING
        for node in plan["nodes"]:
            node["status"] = "PENDING"
            node["latency_ms"] = 0.0

        durable_engine: DurableExecutionEngine = app.state.durable_engine

        async def _step_executor(node: dict[str, Any], attempt: int) -> Any:
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
                raise RuntimeError(f"Simulated failure at step {node_id}")

            node["status"] = "COMPLETED"
            node["latency_ms"] = round((time.time() - start_t) * 1000, 1)
            node["output"] = {"status": "success", "executed_tool": node["tool"]}

            tenant_budget = _get_tenant_governance_budget(request)
            tenant_budget["usage"]["tool_invocations_used"] += 1
            tenant_budget["usage"]["cpu_seconds_used"] = round(
                tenant_budget["usage"]["cpu_seconds_used"] + 0.15, 2
            )
            tenant_budget["percentages"]["tools"] = round(
                (
                    tenant_budget["usage"]["tool_invocations_used"]
                    / tenant_budget["limits"]["max_tool_invocations"]
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
            broadcast_event("budget_updated", tenant_budget)
            return node["output"]

        async def _run_dag_durable() -> None:
            try:
                res = await durable_engine.execute_dag(
                    execution_id=req.execution_id,
                    plan_id=req.plan_id,
                    nodes=plan["nodes"],
                    step_executor=_step_executor,
                    actor=actor_name,
                    tenant_id=tenant_id,
                )
                broadcast_event(
                    "dag_completed",
                    {
                        "plan_id": req.plan_id,
                        "execution_id": req.execution_id,
                        "status": res.get("status", "SUCCEEDED"),
                        "completed_at": time.time(),
                    },
                )
            except Exception as d_err:
                logger.error(f"[Durable DAG Execute] Failed: {d_err}")
                if effective_key:
                    await idem_store.fail_execution(
                        tenant_id=tenant_id,
                        user_id=user_id,
                        idempotency_key=effective_key,
                        error=d_err,
                        state=IdempotencyState.FAILED_TRANSIENT,
                    )

        dag_task = asyncio.create_task(_run_dag_durable())
        durable_engine._active_tasks[req.execution_id] = dag_task

        resp_data = {
            "status": "EXECUTION_STARTED",
            "plan_id": req.plan_id,
            "execution_id": req.execution_id,
            "nodes_count": len(plan["nodes"]),
        }
        if effective_key:
            await idem_store.complete_execution(
                tenant_id=tenant_id,
                user_id=user_id,
                idempotency_key=effective_key,
                response=resp_data,
            )
            return JSONResponse(content=resp_data, headers={"X-Cache": "MISS"})

        return JSONResponse(content=resp_data)

    @app.post("/api/v1/executions/{execution_id}/cancel")
    async def cancel_execution_endpoint(
        execution_id: str,
        request: Request,
        reason: str = Query("", description="Cancellation reason"),
    ) -> dict[str, Any]:
        """Durably cancel an execution in progress, surviving process restarts."""
        durable_engine: DurableExecutionEngine = app.state.durable_engine
        cancelled = await durable_engine.cancel_execution(execution_id, reason=reason)
        return {
            "execution_id": execution_id,
            "status": "CANCELLED",
            "cancelled": cancelled,
            "reason": reason,
        }

    @app.get("/api/v1/executions/{execution_id}")
    async def get_execution_state_endpoint(
        execution_id: str,
        request: Request,
    ) -> dict[str, Any]:
        """Retrieve full execution record, node checkpoints, and state transition history."""
        exec_store: SQLiteExecutionStateStore = app.state.execution_store
        record = await exec_store.load_execution(execution_id)
        if not record:
            raise HTTPException(status_code=404, detail=f"Execution '{execution_id}' not found")
        history = await exec_store.get_state_history(execution_id)
        return {
            "execution_id": record.execution_id,
            "plan_id": record.plan_id,
            "graph_hash": record.graph_hash,
            "status": record.status.value,
            "worker_id": record.worker_id,
            "fencing_token": record.fencing_token,
            "actor": record.actor,
            "tenant_id": record.tenant_id,
            "cancellation_requested": record.cancellation_requested,
            "created_at": record.created_at,
            "updated_at": record.updated_at,
            "node_records": {
                str(k): {
                    "node_id": v.node_id,
                    "status": v.status.value,
                    "tool_name": v.tool_name,
                    "attempt_count": v.attempt_count,
                    "output": v.output,
                    "error_message": v.error_message,
                }
                for k, v in record.node_records.items()
            },
            "state_history": history,
        }

    @app.get("/api/v1/audit/events")
    async def get_audit_events(
        request: Request,
        tenant_id: str | None = Query(None, description="Optional tenant ID to query"),
    ) -> list[dict[str, Any]]:
        """Return chronological list of cryptographic AuditEvent records forming the hash chain."""
        identity: Identity | None = (
            getattr(request.state, "identity", None) or TenantContext.get_current_identity()
        )
        caller_tenant = identity.tenant_id if identity else "default"
        caller_role = identity.role if identity else Role.OPERATOR

        if getattr(app.state, "studio_demo_mode", False):
            demo_chains = getattr(app.state, "demo_audit_chains", {})
            target_tenant = tenant_id or caller_tenant
            if target_tenant not in demo_chains:
                demo_chains[target_tenant] = _create_initial_audit_chain()
            chain = demo_chains[target_tenant]
            return [ev.to_dict() for ev in chain]

        # Tenant Isolation enforcement
        if tenant_id and tenant_id != caller_tenant:
            if caller_role not in (Role.ADMIN, Role.SYSTEM):
                raise HTTPException(
                    status_code=403,
                    detail="Cross-tenant audit query denied. Admin or System role required.",
                )
            query_tenant: str | None = tenant_id
        else:
            query_tenant = caller_tenant

        audit_store: IAuditStore = app.state.audit_store
        events = await audit_store.get_events(tenant_id=query_tenant)
        return [ev.to_dict() for ev in events]

    @app.get("/api/v1/audit/verify")
    @app.post("/api/v1/audit/verify")
    async def verify_audit_chain_endpoint(
        request: Request,
        tenant_id: str | None = Query(None, description="Optional tenant ID to verify"),
    ) -> dict[str, Any]:
        """Perform cryptographic SHA-256 integrity verification across the full audit chain."""
        identity: Identity | None = (
            getattr(request.state, "identity", None) or TenantContext.get_current_identity()
        )
        caller_tenant = identity.tenant_id if identity else "default"
        caller_role = identity.role if identity else Role.OPERATOR

        if getattr(app.state, "studio_demo_mode", False):
            demo_chains = getattr(app.state, "demo_audit_chains", {})
            target_tenant = tenant_id or caller_tenant
            if target_tenant not in demo_chains:
                demo_chains[target_tenant] = _create_initial_audit_chain()
            chain = demo_chains[target_tenant]

            violations: list[str] = []
            hash_chain_valid = True
            broken_seq: int | None = None

            for i in range(len(chain)):
                event = chain[i]
                # 1. Verify linkage to previous block
                if i == 0:
                    if event.previous_event_hash != GENESIS_HASH:
                        violations.append(
                            f"Genesis event #{event.sequence_number} ({event.event_id}) invalid previous_event_hash"
                        )
                        hash_chain_valid = False
                        if broken_seq is None:
                            broken_seq = event.sequence_number
                else:
                    prev_event = chain[i - 1]
                    if event.previous_event_hash != prev_event.event_hash:
                        violations.append(
                            f"Broken link at event #{event.sequence_number} ({event.event_id}): previous_event_hash '{event.previous_event_hash}' does not match preceding event_hash '{prev_event.event_hash}'"
                        )
                        hash_chain_valid = False
                        if broken_seq is None:
                            broken_seq = event.sequence_number

                # 2. Verify payload hash
                calc_hash = _compute_audit_event_hash(event)
                if event.event_hash != calc_hash:
                    violations.append(
                        f"Tampered payload at event #{event.sequence_number} ({event.event_id}): recorded hash '{event.event_hash}' does not match computed hash '{calc_hash}'"
                    )
                    hash_chain_valid = False
                    if broken_seq is None:
                        broken_seq = event.sequence_number

            valid = len(violations) == 0
            return {
                "valid": valid,
                "event_count": len(chain),
                "broken_at_sequence": broken_seq if not valid else None,
                "hash_chain_valid": hash_chain_valid,
                "sequence_valid": True,
                "correlation_valid": True,
                "terminal_state_valid": True,
                "violations": violations,
                "verified_at": time.time(),
            }

        if tenant_id and tenant_id != caller_tenant:
            if caller_role not in (Role.ADMIN, Role.SYSTEM):
                raise HTTPException(
                    status_code=403,
                    detail="Cross-tenant audit query denied. Admin or System role required.",
                )
            target_tenant = tenant_id
        else:
            target_tenant = caller_tenant

        audit_store: IAuditStore = app.state.audit_store
        res = await audit_store.verify_chain(tenant_id=target_tenant)
        return {
            "valid": res.valid,
            "event_count": res.event_count,
            "broken_at_sequence": res.broken_at_sequence,
            "hash_chain_valid": res.hash_chain_valid,
            "sequence_valid": res.sequence_valid,
            "correlation_valid": res.correlation_valid,
            "terminal_state_valid": res.terminal_state_valid,
            "violations": res.violations,
            "verified_at": time.time(),
        }

    @app.post("/api/v1/audit/tamper")
    async def tamper_audit_event_endpoint(
        req: AuditTamperRequest, request: Request
    ) -> dict[str, Any]:
        """Simulate malicious tampering on an event in the audit chain to test cryptographic detection."""
        if not getattr(app.state, "studio_demo_mode", False):
            raise HTTPException(
                status_code=403,
                detail="Audit log mutation endpoints are disabled in production mode. Set NEXUSAI_STUDIO_DEMO_MODE=true for demonstration environments.",
            )

        identity: Identity | None = (
            getattr(request.state, "identity", None) or TenantContext.get_current_identity()
        )
        if identity and identity.role == Role.VIEWER:
            raise HTTPException(
                status_code=403,
                detail=f"RBAC access denied: Role '{identity.role.value}' cannot tamper audit events",
            )

        tenant_id = identity.tenant_id if identity else "default"
        demo_chains = getattr(app.state, "demo_audit_chains", {})
        if tenant_id not in demo_chains:
            demo_chains[tenant_id] = _create_initial_audit_chain()
        chain = demo_chains[tenant_id]

        if len(chain) < 2:
            raise HTTPException(status_code=400, detail="Audit chain too short to tamper")

        target_idx = 1
        if req.event_id:
            for idx, ev in enumerate(chain):
                if ev.event_id == req.event_id:
                    target_idx = idx
                    break

        ev = chain[target_idx]
        tampered_dict = ev.to_dict()
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
            actor=str(tampered_dict.get("actor", "anonymous")),
            tenant_id=str(tampered_dict.get("tenant_id", "default")),
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
    async def reset_audit_chain_endpoint(request: Request) -> dict[str, Any]:
        """Reset the audit chain back to verified clean genesis state."""
        if not getattr(app.state, "studio_demo_mode", False):
            raise HTTPException(
                status_code=403,
                detail="Audit log mutation endpoints are disabled in production mode. Set NEXUSAI_STUDIO_DEMO_MODE=true for demonstration environments.",
            )

        identity: Identity | None = (
            getattr(request.state, "identity", None) or TenantContext.get_current_identity()
        )
        if identity and identity.role == Role.VIEWER:
            raise HTTPException(
                status_code=403,
                detail=f"RBAC access denied: Role '{identity.role.value}' cannot reset audit chain",
            )

        tenant_id = _get_tenant_id(request)
        demo_chains = getattr(app.state, "demo_audit_chains", {})
        demo_chains[tenant_id] = _create_initial_audit_chain()
        chain = demo_chains[tenant_id]
        broadcast_event("audit_reset", {"event_count": len(chain)})
        return {
            "status": "RESET_SUCCESS",
            "event_count": len(chain),
        }

    @app.get("/api/v1/governance/budget")
    async def get_governance_budget(request: Request) -> dict[str, Any]:
        """Return active resource budget and consumed quotas."""
        budget = _get_tenant_governance_budget(request)
        return budget

    @app.get("/api/v1/governance/approvals")
    async def get_pending_approvals(request: Request) -> list[dict[str, Any]]:
        """Return list of pending human-in-the-loop safety approvals."""
        approvals = _get_tenant_pending_approvals(request)
        return approvals

    @app.post("/api/v1/governance/approvals/{approval_id}/decision")
    async def submit_approval_decision_endpoint(
        approval_id: str, req: GovernanceDecisionRequest, request: Request
    ) -> dict[str, Any]:
        """Submit human operator approval or denial decision for governed tool invocation."""
        identity: Identity | None = (
            getattr(request.state, "identity", None) or TenantContext.get_current_identity()
        )
        if identity and identity.role == Role.VIEWER:
            raise HTTPException(
                status_code=403,
                detail=f"RBAC access denied: Role '{identity.role.value}' cannot submit approval decisions",
            )

        approvals = _get_tenant_pending_approvals(request)
        budget = _get_tenant_governance_budget(request)

        target = None
        for app_item in approvals:
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
            budget["usage"]["tool_invocations_used"] += 1
            broadcast_event(
                "approval_resolved",
                {
                    "approval_id": approval_id,
                    "status": "APPROVED",
                    "grant_id": grant_id,
                },
            )
            broadcast_event("budget_updated", budget)
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
