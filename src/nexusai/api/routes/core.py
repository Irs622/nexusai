"""Health probes, status, tool catalog, chat, approvals, and direct tool execution."""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request, Response
from fastapi.responses import JSONResponse

from nexusai.api.common import internal_error
from nexusai.api.context import ServerContext
from nexusai.api.schemas import ApprovalRequest, ChatRequest, ToolExecRequest
from nexusai.bus.commands import ExecuteToolCommand
from nexusai.core.errors import (
    IdempotencyConflictError,
    IdempotencyPayloadMismatchError,
    SecurityError,
)
from nexusai.infrastructure.idempotency import (
    IdempotencyState,
    compute_payload_fingerprint,
)
from nexusai.infrastructure.observability.redaction import sanitize_secrets_recursive
from nexusai.security.guard import RiskLevel
from nexusai.security.identity import Identity, Role, TenantContext

# Import Tools & MCP


def build_router(ctx: ServerContext) -> APIRouter:
    """Create the router for this endpoint group bound to ``ctx`` services."""
    router = APIRouter()
    config = ctx.config
    security_guard = ctx.security_guard
    command_bus = ctx.command_bus
    registry = ctx.registry
    context_engine = ctx.context_engine
    idem_store = ctx.idem_store
    coordinator = ctx.coordinator
    _get_tenant_pending_approvals = ctx.get_tenant_pending_approvals

    # =========================================================================
    # CORE REST ENDPOINTS & HEALTH PROBES
    # =========================================================================

    @router.get("/health/live")
    @router.get("/healthz")
    async def liveness() -> dict[str, str]:
        """Kubernetes liveness probe endpoint."""
        return {"status": "ok"}

    @router.get("/health/ready")
    @router.get("/readyz")
    async def readiness() -> dict[str, str]:
        """Kubernetes readiness probe endpoint."""
        return {"status": "ready"}

    @router.get("/api/status")
    async def get_status() -> dict[str, Any]:
        working_ctx = await context_engine.gather_context()
        return {
            "status": "OPERATIONAL",
            "environment": config.app.environment,
            "default_model": f"{config.models.default_provider}/{config.models.default_model}",
            "strict_security": config.security.strict_mode,
            "context": working_ctx.model_dump(),
        }

    @router.get("/api/tools")
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

    @router.post("/api/chat")
    async def chat_endpoint(req: ChatRequest, request: Request) -> dict[str, Any]:
        identity: Identity | None = (
            getattr(request.state, "identity", None) or TenantContext.get_current_identity()
        )
        if identity and identity.role == Role.VIEWER:
            raise HTTPException(
                status_code=403,
                detail=f"RBAC access denied: Role '{identity.role.value}' is read-only and cannot invoke chat",
            )
        tenant_id = identity.tenant_id if identity else "default"
        user_id = identity.user_id if identity else "anonymous"
        try:
            res = await coordinator.process_user_input(
                user_text=req.prompt,
                session_id=req.session_id or "",
                approval_token=req.approval_token,
                user_id=user_id,
                tenant_id=tenant_id,
            )
            return res
        except SecurityError as sec_err:
            raise HTTPException(status_code=403, detail=str(sec_err)) from sec_err
        except Exception as e:
            raise internal_error("/api/chat", e) from e

    @router.post("/api/v1/approvals/request")
    async def request_approval_token(req: ApprovalRequest, request: Request) -> dict[str, Any]:
        """Submit an approval request. Only ADMIN role may self-issue a token immediately.
        All other callers create a PENDING request that requires explicit supervisor approval.
        [AUDIT-04] Requesting an approval token must NOT itself constitute approval.
        """
        identity: Identity | None = (
            getattr(request.state, "identity", None) or TenantContext.get_current_identity()
        )
        user_id = identity.user_id if identity else "anonymous"
        tenant_id = identity.tenant_id if identity else "default"
        caller_role: Role = identity.role if identity else Role.VIEWER

        # Only ADMIN may immediately issue an approval token (e.g., for scripted/automated pipelines).
        # All other roles must wait for an authorised supervisor to grant approval.
        if caller_role == Role.ADMIN:
            try:
                token, expires_at = security_guard.approval_service.create_token(
                    tool_name=req.tool_name,
                    arguments=req.arguments,
                    user_id=user_id,
                    execution_id=req.execution_id,
                )
                return {"approval_token": token, "expires_at": expires_at, "status": "APPROVED"}
            except Exception as e:
                raise HTTPException(status_code=400, detail=str(e)) from e

        # Non-admin: create a pending approval request and return PENDING state.
        import uuid as _uuid

        pending_id = str(_uuid.uuid4())
        try:
            risk_level = registry.get(req.tool_name).risk_level.value
        except Exception:
            risk_level = "UNKNOWN"
        pending_approvals = _get_tenant_pending_approvals(request)
        # Same record shape as the governance approval queue, so supervisors can resolve it
        # via POST /api/v1/governance/approvals/{approval_id}/decision.
        pending_approvals.append(
            {
                "approval_id": pending_id,
                "tool_name": req.tool_name,
                "arguments": req.arguments,
                "parameters": req.arguments,
                "execution_id": req.execution_id,
                "requested_by": user_id,
                "tenant_id": tenant_id,
                "risk_level": risk_level,
                "status": "PENDING",
                "created_at": time.time(),
                "bound_request": True,
            }
        )
        return {
            "approval_id": pending_id,
            "status": "PENDING_REVIEW",
            "message": "Approval request submitted. An authorized supervisor must approve before execution can proceed.",
        }

    @router.get("/api/v1/approvals/{approval_id}")
    async def get_approval_request(approval_id: str, request: Request) -> dict[str, Any]:
        """Return the state of an approval request; the requester receives the issued token."""
        identity: Identity | None = (
            getattr(request.state, "identity", None) or TenantContext.get_current_identity()
        )
        user_id = identity.user_id if identity else "anonymous"

        target = next(
            (
                item
                for item in _get_tenant_pending_approvals(request)
                if item.get("approval_id") == approval_id and item.get("bound_request")
            ),
            None,
        )
        if target is None:
            raise HTTPException(
                status_code=404, detail=f"Approval request '{approval_id}' not found"
            )

        is_admin = identity is not None and identity.role == Role.ADMIN
        if target["requested_by"] != user_id and not is_admin:
            raise HTTPException(
                status_code=403, detail="Only the requester may read this approval request"
            )

        result = {k: v for k, v in target.items() if k != "approval_token"}
        if target["requested_by"] == user_id and "approval_token" in target:
            result["approval_token"] = target["approval_token"]
        return result

    @router.post("/api/tools/execute")
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

        if identity is None:
            # No authenticated identity (auth disabled): never allow HIGH/CRITICAL tools.
            if tool.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL):
                raise HTTPException(
                    status_code=403,
                    detail=f"RBAC access denied: {tool.risk_level.value} risk tool '{req.tool_name}' requires an authenticated identity",
                )
        else:
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

    return router
