"""FastAPI composition root for the NexusAI Web Dashboard API.

Service wiring lives in :mod:`nexusai.api.bootstrap`; endpoint groups live in
:mod:`nexusai.api.routes`. This module assembles them and keeps the historical
import surface (``create_app``, ``app``, request schemas) stable.
"""

from __future__ import annotations

from dotenv import find_dotenv, load_dotenv
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

load_dotenv(find_dotenv(usecwd=True))

from nexusai.api.bootstrap import build_context  # noqa: E402
from nexusai.api.common import _internal_error, internal_error, web_dir  # noqa: E402,F401
from nexusai.api.demo_data import (  # noqa: E402,F401
    _compute_audit_event_hash,
    _create_initial_audit_chain,
    _create_initial_governance_budget,
    _create_initial_pending_approvals,
    _create_studio_plans,
)
from nexusai.api.routes import audit, core, dag, events, governance, mcp  # noqa: E402
from nexusai.api.schemas import (  # noqa: E402,F401
    ApprovalRequest,
    AuditTamperRequest,
    ChatRequest,
    DagExecuteRequest,
    GovernanceDecisionRequest,
    ToolExecRequest,
)
from nexusai.automation.scheduler import SchedulerService  # noqa: E402
from nexusai.brain.ports.audit_store_port import IAuditStore  # noqa: E402
from nexusai.infrastructure.idempotency import IdempotencyStore  # noqa: E402
from nexusai.tools.knowledge import VectorKnowledgeBase  # noqa: E402

# Registration order is significant for route matching; keep it stable.
_ROUTE_GROUPS = (core, mcp, events, dag, audit, governance)


def create_app(
    db_path: str = ":memory:",
    vector_kb: VectorKnowledgeBase | None = None,
    scheduler: SchedulerService | None = None,
    idempotency_store: IdempotencyStore | None = None,
    audit_store: IAuditStore | None = None,
    studio_demo_mode: bool | None = None,
) -> FastAPI:
    """Create and configure FastAPI application for NexusAI Web Dashboard."""
    ctx = build_context(
        db_path=db_path,
        vector_kb=vector_kb,
        scheduler=scheduler,
        idempotency_store=idempotency_store,
        audit_store=audit_store,
        studio_demo_mode=studio_demo_mode,
    )
    app = ctx.app
    for group in _ROUTE_GROUPS:
        # Routers carry no prefix/dependencies, so their routes are appended flat. This
        # keeps ``app.routes`` a plain list of APIRoute objects, as before the split.
        app.router.routes.extend(group.build_router(ctx).routes)

    if web_dir.exists():
        app.mount("/static", StaticFiles(directory=str(web_dir)), name="static")

        @app.get("/")
        async def serve_index() -> FileResponse:
            return FileResponse(web_dir / "index.html")

    return app


app = create_app()
