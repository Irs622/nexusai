"""Shared service container passed from the composition root to every API router."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any, cast

from fastapi import FastAPI, Request

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
from nexusai.context.engine import ContextEngine
from nexusai.core.config import SystemConfig
from nexusai.infrastructure.idempotency import (
    IdempotencyStore,
)
from nexusai.infrastructure.persistence.sqlite_execution_coordinator import (
    SQLiteExecutionCoordinator,
)
from nexusai.infrastructure.persistence.sqlite_execution_journal import SQLiteExecutionJournal
from nexusai.infrastructure.persistence.sqlite_execution_store import SQLiteExecutionStateStore
from nexusai.logging.logger import logger
from nexusai.memory.sqlite_memory import SQLiteMemory
from nexusai.runtime.execution_engine import DurableExecutionEngine
from nexusai.runtime.recovery import CrashRecoveryProtocol
from nexusai.security.authentication import ApiKeyService
from nexusai.security.guard import SecurityGuard
from nexusai.security.identity import Identity, Role, TenantContext

# Import Tools & MCP
from nexusai.tools.mcp import McpServerManager
from nexusai.tools.registry import ToolRegistry


@dataclass
class ServerContext:
    """Services and configuration shared by the API routers of one application instance."""

    app: FastAPI
    config: SystemConfig
    security_guard: SecurityGuard
    event_bus: EventBus
    command_bus: CommandBus
    registry: ToolRegistry
    context_engine: ContextEngine
    sched_service: SchedulerService
    mcp_manager: McpServerManager
    idem_store: IdempotencyStore
    aud_store: IAuditStore
    is_demo_mode: bool
    exec_store: SQLiteExecutionStateStore
    exec_journal: SQLiteExecutionJournal
    exec_coord: SQLiteExecutionCoordinator
    api_worker: WorkerIdentity
    durable_engine: DurableExecutionEngine
    crash_recovery: CrashRecoveryProtocol
    memory: SQLiteMemory
    coordinator: BrainCoordinator
    api_key_service: ApiKeyService
    auth_enabled: bool
    is_production: bool

    def get_tenant_id(self, req: Request) -> str:
        """Resolve the caller's tenant from request identity, defaulting to ``default``."""
        ident: Identity | None = (
            getattr(req.state, "identity", None) or TenantContext.get_current_identity()
        )
        if ident and ident.tenant_id:
            return ident.tenant_id
        return "default"

    def get_tenant_audit_chain(self, req: Request) -> list[AuditEvent]:
        """Return (creating on first use) the tenant's simulated audit chain."""
        t_id = self.get_tenant_id(req)
        chains = self.app.state.tenant_audit_chains
        if t_id not in chains:
            chains[t_id] = _create_initial_audit_chain()
        return cast(list[AuditEvent], chains[t_id])

    def get_tenant_governance_budget(self, req: Request) -> dict[str, Any]:
        """Return (creating on first use) the tenant's simulated governance budget."""
        t_id = self.get_tenant_id(req)
        budgets = self.app.state.tenant_governance_budgets
        if t_id not in budgets:
            budgets[t_id] = _create_initial_governance_budget()
        return cast(dict[str, Any], budgets[t_id])

    def get_tenant_pending_approvals(self, req: Request) -> list[dict[str, Any]]:
        """Return (creating on first use) the tenant's simulated pending approvals."""
        t_id = self.get_tenant_id(req)
        approvals = self.app.state.tenant_pending_approvals
        if t_id not in approvals:
            approvals[t_id] = _create_initial_pending_approvals()
        return cast(list[dict[str, Any]], approvals[t_id])

    def get_tenant_studio_plans(self, req: Request) -> dict[str, Any]:
        """Return (creating on first use) the tenant's Studio DAG plans."""
        t_id = self.get_tenant_id(req)
        plans = self.app.state.tenant_studio_plans
        if t_id not in plans:
            plans[t_id] = _create_studio_plans()
        return cast(dict[str, Any], plans[t_id])

    def broadcast_event(
        self, event_name: str, payload: dict[str, Any], tenant_id: str | None = None
    ) -> None:
        """Broadcast real-time event to authorized SSE clients scoped by tenant."""
        msg = f"event: {event_name}\ndata: {json.dumps(payload)}\n\n"
        subscribers: list[Any] = getattr(self.app.state, "event_subscribers", [])
        for sub in list(subscribers):
            try:
                if isinstance(sub, dict):
                    sub_role = sub.get("role")
                    sub_tenant = sub.get("tenant_id")
                    if (
                        tenant_id is None
                        or sub_role in (Role.ADMIN, Role.SYSTEM)
                        or sub_tenant == tenant_id
                    ):
                        sub["queue"].put_nowait(msg)
                elif isinstance(sub, asyncio.Queue):
                    sub.put_nowait(msg)
            except Exception as exc:
                logger.warning("broadcast_event: best-effort operation failed: {!r}", exc)
