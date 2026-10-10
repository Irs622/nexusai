"""Service wiring for the NexusAI API: core services, durable execution, and auth."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from nexusai.api.context import ServerContext
from nexusai.api.demo_data import (
    _create_initial_audit_chain,
    _create_initial_governance_budget,
    _create_initial_pending_approvals,
    _create_studio_plans,
)
from nexusai.automation.scheduler import SchedulerService
from nexusai.brain.coordinator import BrainCoordinator
from nexusai.brain.domain.audit import AuditEvent
from nexusai.brain.domain.execution_coordination import WorkerIdentity
from nexusai.brain.ports.audit_store_port import IAuditStore
from nexusai.bus.bus import CommandBus, EventBus
from nexusai.bus.commands import ExecuteToolCommand, ExecuteToolCommandHandler
from nexusai.context.engine import ContextEngine
from nexusai.core.config import SystemConfig
from nexusai.core.errors import (
    ConfigurationError,
)
from nexusai.infrastructure.idempotency import (
    IdempotencyStore,
    InMemoryIdempotencyStore,
)
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
from nexusai.security.guard import SecurityGuard
from nexusai.security.identity import Role
from nexusai.security.rate_limiter import create_rate_limiter

# Import Tools & MCP
from nexusai.tools.automation import ScheduleReminderTool
from nexusai.tools.knowledge import RecallFactTool, RememberFactTool, VectorKnowledgeBase
from nexusai.tools.macos import GetActiveWindowTool, NotifyTool, OpenAppTool, RawAppleScriptTool
from nexusai.tools.mcp import McpServerManager
from nexusai.tools.registry import ToolRegistry
from nexusai.tools.system import TerminalTool
from nexusai.tools.vision import ScreenCaptureTool
from nexusai.tools.workspace import GitStatusTool, ListDirectoryTool, ReadFileTool


def build_context(
    db_path: str = ":memory:",
    vector_kb: VectorKnowledgeBase | None = None,
    scheduler: SchedulerService | None = None,
    idempotency_store: IdempotencyStore | None = None,
    audit_store: IAuditStore | None = None,
    studio_demo_mode: bool | None = None,
) -> ServerContext:
    """Construct services, the FastAPI app (with lifespan and middleware), and its context."""
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

    # NEX-010: Topology validation: multi-replica or production mode requires shared persistent backends
    is_prod = os.getenv("NEXUSAI_ENV") in ("production", "prod") or (
        config
        and getattr(getattr(config, "app", None), "environment", "") in ("production", "prod")
    )
    replica_count = int(os.getenv("NEXUSAI_REPLICAS", "1"))
    if (is_prod or replica_count > 1) and (
        exec_db_path == ":memory:" or coord_db_path == ":memory:"
    ):
        raise ConfigurationError(
            "Production / multi-replica deployment aborted: NEXUSAI_EXECUTION_DB and NEXUSAI_COORDINATOR_DB "
            "cannot be ':memory:'. A durable shared storage backend or persistent volume path must be configured."
        )

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
    key_storage_path = os.getenv("NEXUSAI_KEY_STORAGE_PATH") or (
        auth_cfg.key_storage_path if auth_cfg else None
    )
    api_key_service = ApiKeyService(
        storage_path=key_storage_path,
        default_rate_limit=auth_cfg.rate_limit_per_minute if auth_cfg else 100,
        rate_limiter=create_rate_limiter(),
    )

    # Environment mode detection
    is_production = os.getenv("NEXUSAI_ENV") in ("production", "prod") or (
        config
        and getattr(getattr(config, "app", None), "environment", "") in ("production", "prod")
    )

    auth_enabled = (
        auth_cfg.enabled
        if (auth_cfg and os.getenv("NEXUSAI_AUTH_ENABLED", "true").lower() != "false")
        else True
    )
    if os.getenv("NEXUSAI_AUTH_ENABLED", "").lower() == "false":
        auth_enabled = False

    # [AUDIT-06] Fail-closed invariant: authentication cannot be disabled in production
    if is_production and not auth_enabled:
        raise ConfigurationError(
            "Production startup aborted: Authentication cannot be disabled when running in production mode. "
            "Set NEXUSAI_AUTH_ENABLED=true or remove the override to start in production."
        )

    # NEX-002: Production credential hardening - eliminate hardcoded admin fallback in production
    configured_admin_key = os.getenv("NEXUSAI_ADMIN_API_KEY") or os.getenv("NEXUSAI_TEST_API_KEY")
    if is_production:
        if configured_admin_key == "nx_test_admin_key_123":
            raise ConfigurationError(
                "Production startup aborted: Default test key 'nx_test_admin_key_123' is strictly forbidden in production."
            )
        if configured_admin_key:
            api_key_service.register_raw_key(
                raw_key=configured_admin_key,
                tenant_id="default",
                user_id="admin-user",
                role=Role.ADMIN,
                name="Production Administrative Key",
            )
        elif auth_enabled and not api_key_service.list_keys():
            raise ConfigurationError(
                "Production startup aborted: Authentication is enabled but no administrative API key is provisioned. "
                "Configure NEXUSAI_ADMIN_API_KEY or supply keys via config/api_keys.json."
            )
    else:
        # Development / Testing mode: register development test key with prominent warning
        dev_key = configured_admin_key or "nx_test_admin_key_123"
        if dev_key == "nx_test_admin_key_123":
            logger.warning(
                "DEVELOPMENT/TEST MODE: Registering hardcoded administrative test key 'nx_test_admin_key_123'. "
                "This fallback is strictly disabled and rejected in production mode."
            )
        api_key_service.register_raw_key(
            raw_key=dev_key,
            tenant_id="default",
            user_id="admin-user",
            role=Role.ADMIN,
            name="Development Admin Key",
        )

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

    return ServerContext(
        app=app,
        config=config,
        security_guard=security_guard,
        event_bus=event_bus,
        command_bus=command_bus,
        registry=registry,
        context_engine=context_engine,
        sched_service=sched_service,
        mcp_manager=mcp_manager,
        idem_store=idem_store,
        aud_store=aud_store,
        is_demo_mode=is_demo_mode,
        exec_store=exec_store,
        exec_journal=exec_journal,
        exec_coord=exec_coord,
        api_worker=api_worker,
        durable_engine=durable_engine,
        crash_recovery=crash_recovery,
        memory=memory,
        coordinator=coordinator,
        api_key_service=api_key_service,
        auth_enabled=auth_enabled,
        is_production=bool(is_production),
    )
