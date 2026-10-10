"""Studio DAG plans, DAG execution, and durable execution inspection/cancellation."""

from __future__ import annotations

import asyncio
import os
import time
from typing import Any, cast

from fastapi import APIRouter, Header, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse

from nexusai.api.context import ServerContext
from nexusai.api.schemas import DagExecuteRequest
from nexusai.core.errors import (
    IdempotencyConflictError,
    IdempotencyPayloadMismatchError,
)
from nexusai.infrastructure.idempotency import (
    IdempotencyState,
    compute_payload_fingerprint,
)
from nexusai.infrastructure.persistence.sqlite_execution_store import SQLiteExecutionStateStore
from nexusai.logging.logger import logger
from nexusai.runtime.execution_engine import DurableExecutionEngine
from nexusai.security.execution_policy import ExecutionAccessPolicy
from nexusai.security.identity import Identity, Role, TenantContext

# Import Tools & MCP


def build_router(ctx: ServerContext) -> APIRouter:
    """Create the router for this endpoint group bound to ``ctx`` services."""
    router = APIRouter()
    app = ctx.app
    idem_store = ctx.idem_store
    auth_enabled = ctx.auth_enabled
    _get_tenant_governance_budget = ctx.get_tenant_governance_budget
    _get_tenant_studio_plans = ctx.get_tenant_studio_plans
    broadcast_event = ctx.broadcast_event

    # =========================================================================
    # NEXUSAI STUDIO: DAG WORKFLOW & AUDIT CHAIN VISUALIZER (ISSUE #24, #29)
    # NOTE: The Studio DAG endpoints below operate as an interactive visualization
    # and demonstration layer (simulated execution mode). Step transitions and
    # timings simulate node latency (asyncio.sleep) and broadcast state over SSE
    # for interactive operator observation, rather than executing live tasks
    # against real external systems. All Studio DAG endpoints return the header
    # 'X-NexusAI-Mode: simulation' to explicitly declare this simulation nature.
    # =========================================================================

    @router.get("/api/v1/dag/plans")
    async def get_dag_plans(request: Request, response: Response) -> list[dict[str, Any]]:
        """Return available DAG plan templates with metadata (Simulation Mode)."""
        response.headers["X-NexusAI-Mode"] = "simulation"
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

    @router.get("/api/v1/dag/current")
    async def get_current_dag(
        request: Request, response: Response, plan_id: str = "incident_response"
    ) -> dict[str, Any]:
        """Return full PlanGraph nodes and edge specifications for specified plan (Simulation Mode)."""
        response.headers["X-NexusAI-Mode"] = "simulation"
        plans_dict = _get_tenant_studio_plans(request)
        plan = plans_dict.get(plan_id)
        if not plan:
            raise HTTPException(status_code=404, detail=f"Plan '{plan_id}' not found")
        return cast(dict[str, Any], plan)

    @router.post("/api/v1/dag/execute")
    @router.post("/api/v1/execute")
    async def execute_dag_plan(
        req: DagExecuteRequest,
        request: Request,
        x_idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    ) -> Response:
        """Trigger execution of a DAG plan, broadcasting live node transitions via SSE (Simulation Mode)."""
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
                        headers={"Retry-After": "2", "X-NexusAI-Mode": "simulation"},
                    )
                if record.state == IdempotencyState.SUCCEEDED:
                    return JSONResponse(
                        content=record.response,
                        headers={"X-Cache": "HIT", "X-NexusAI-Mode": "simulation"},
                    )
                if record.state == IdempotencyState.FAILED_TERMINAL:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Cached terminal failure: {record.error_message}",
                        headers={"X-Cache": "HIT", "X-NexusAI-Mode": "simulation"},
                    )

        # Persist execution state to SQLite before tool invocation begins
        exec_store: SQLiteExecutionStateStore = app.state.execution_store
        existing_exec = await exec_store.load_execution(req.execution_id)
        if existing_exec and existing_exec.tenant_id != tenant_id:
            raise HTTPException(
                status_code=409,
                detail=f"Execution ID '{req.execution_id}' already belongs to another tenant",
            )
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

        # Studio Demonstration Step Executor (Simulation Mode):
        # This simulates node latency (0.18s) and telemetry transitions for the
        # frontend visualization layer rather than executing live production tasks.
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
                tenant_id=tenant_id,
            )

            # Simulated node processing delay (visualization harness)
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
                    tenant_id=tenant_id,
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
                tenant_id=tenant_id,
            )
            broadcast_event("budget_updated", tenant_budget, tenant_id=tenant_id)
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
                    tenant_id=tenant_id,
                )
                # NEX-007: Only mark idempotency SUCCEEDED after actual background DAG completion
                if effective_key:
                    dag_result = {
                        "status": "COMPLETED",
                        "plan_id": req.plan_id,
                        "execution_id": req.execution_id,
                        "result": res,
                    }
                    await idem_store.complete_execution(
                        tenant_id=tenant_id,
                        user_id=user_id,
                        idempotency_key=effective_key,
                        response=dag_result,
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
        resp_headers = {"X-NexusAI-Mode": "simulation"}
        if effective_key:
            # NEX-007: Record stays in RUNNING state while task executes in background
            resp_headers["X-Cache"] = "MISS"
            return JSONResponse(content=resp_data, headers=resp_headers)

        return JSONResponse(content=resp_data, headers=resp_headers)

    @router.post("/api/v1/executions/{execution_id}/cancel")
    async def cancel_execution_endpoint(
        execution_id: str,
        request: Request,
        reason: str = Query("", description="Cancellation reason"),
    ) -> dict[str, Any]:
        """Durably cancel an execution in progress, surviving process restarts."""
        identity: Identity | None = (
            getattr(request.state, "identity", None) or TenantContext.get_current_identity()
        )

        exec_store: SQLiteExecutionStateStore = app.state.execution_store
        record = await exec_store.load_execution(execution_id)
        if not record:
            raise HTTPException(status_code=404, detail=f"Execution '{execution_id}' not found")

        # RBAC & Object-level authorization enforcement
        if identity and identity.role == Role.VIEWER:
            raise HTTPException(
                status_code=403,
                detail="RBAC access denied: Viewer role cannot cancel executions",
            )

        if not ExecutionAccessPolicy.can_cancel(identity, record.tenant_id):
            raise HTTPException(
                status_code=403,
                detail="Cross-tenant execution cancellation denied. Admin or System role required.",
            )

        durable_engine: DurableExecutionEngine = app.state.durable_engine
        effective_tenant = (
            None
            if (identity and identity.role in (Role.ADMIN, Role.SYSTEM))
            else (identity.tenant_id if identity else None)
        )
        cancelled = await durable_engine.cancel_execution(
            execution_id,
            reason=reason,
            tenant_id=effective_tenant,
        )
        return {
            "execution_id": execution_id,
            "status": "CANCELLED",
            "cancelled": cancelled,
            "reason": reason,
        }

    @router.get("/api/v1/executions/{execution_id}")
    async def get_execution_state_endpoint(
        execution_id: str,
        request: Request,
    ) -> dict[str, Any]:
        """Retrieve full execution record, node checkpoints, and state transition history."""
        identity: Identity | None = (
            getattr(request.state, "identity", None) or TenantContext.get_current_identity()
        )

        exec_store: SQLiteExecutionStateStore = app.state.execution_store
        record = await exec_store.load_execution(execution_id)
        if not record:
            raise HTTPException(status_code=404, detail=f"Execution '{execution_id}' not found")

        # Object-level authorization enforcement (BOLA / IDOR protection)
        if not ExecutionAccessPolicy.can_read(identity, record.tenant_id):
            raise HTTPException(
                status_code=403,
                detail="Cross-tenant execution access denied. Admin or System role required.",
            )

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

    return router
