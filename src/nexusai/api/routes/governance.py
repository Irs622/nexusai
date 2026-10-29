"""Governance budget and approval decision endpoints."""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response

from nexusai.api.context import ServerContext
from nexusai.api.schemas import GovernanceDecisionRequest
from nexusai.security.identity import Identity, Role, TenantContext

# Import Tools & MCP


def build_router(ctx: ServerContext) -> APIRouter:
    """Create the router for this endpoint group bound to ``ctx`` services."""
    router = APIRouter()
    _get_tenant_id = ctx.get_tenant_id
    _get_tenant_governance_budget = ctx.get_tenant_governance_budget
    _get_tenant_pending_approvals = ctx.get_tenant_pending_approvals
    broadcast_event = ctx.broadcast_event
    security_guard = ctx.security_guard

    @router.get("/api/v1/governance/budget")
    async def get_governance_budget(request: Request, response: Response) -> dict[str, Any]:
        """Return active resource budget and consumed quotas."""
        response.headers["X-NexusAI-Mode"] = "simulation"
        budget = _get_tenant_governance_budget(request)
        return budget

    @router.get("/api/v1/governance/approvals")
    async def get_pending_approvals(request: Request, response: Response) -> list[dict[str, Any]]:
        """Return list of pending human-in-the-loop safety approvals."""
        response.headers["X-NexusAI-Mode"] = "simulation"
        approvals = _get_tenant_pending_approvals(request)
        # Issued tokens are only handed to the requester (GET /api/v1/approvals/{id}).
        return [{k: v for k, v in item.items() if k != "approval_token"} for item in approvals]

    @router.post("/api/v1/governance/approvals/{approval_id}/decision")
    async def submit_approval_decision_endpoint(
        approval_id: str, req: GovernanceDecisionRequest, request: Request, response: Response
    ) -> dict[str, Any]:
        """Submit human operator approval or denial decision for governed tool invocation."""
        response.headers["X-NexusAI-Mode"] = "simulation"
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

        if req.decision not in ("APPROVED", "DENIED"):
            raise HTTPException(status_code=400, detail="decision must be APPROVED or DENIED")

        # Requests raised via /api/v1/approvals/request are bound to a concrete tool call:
        # they need an authenticated decider who is not the requester (separation of duties).
        is_bound = bool(target.get("bound_request"))
        if is_bound:
            if identity is None:
                raise HTTPException(
                    status_code=403,
                    detail="An authenticated identity is required to resolve approval requests",
                )
            if identity.user_id == target["requested_by"]:
                raise HTTPException(
                    status_code=403,
                    detail="Requesters cannot approve or deny their own approval requests",
                )

        approval_token: str | None = None
        if is_bound and req.decision == "APPROVED":
            approval_token, _ = security_guard.approval_service.create_token(
                tool_name=target["tool_name"],
                arguments=target["arguments"],
                user_id=target["requested_by"],
                execution_id=target["execution_id"],
            )
            target["approval_token"] = approval_token

        actor = identity.user_id if identity else req.actor
        target["status"] = req.decision
        target["resolved_at"] = time.time()
        target["actor"] = actor

        tenant_id = _get_tenant_id(request)
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
                tenant_id=tenant_id,
            )
            broadcast_event("budget_updated", budget, tenant_id=tenant_id)
            return {
                "approval_id": approval_id,
                "status": "APPROVED",
                "grant_id": grant_id,
                "actor": actor,
                "token_issued": approval_token is not None,
            }
        else:
            broadcast_event(
                "approval_resolved",
                {
                    "approval_id": approval_id,
                    "status": "DENIED",
                },
                tenant_id=tenant_id,
            )
            return {
                "approval_id": approval_id,
                "status": "DENIED",
                "actor": actor,
            }

    return router
