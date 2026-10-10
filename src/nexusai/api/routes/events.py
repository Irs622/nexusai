"""SSE stream-token issuance and the real-time Server-Sent Events stream."""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any, AsyncGenerator, cast

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from nexusai.api.context import ServerContext
from nexusai.security.identity import Identity, Role, TenantContext

# Import Tools & MCP


def build_router(ctx: ServerContext) -> APIRouter:
    """Create the router for this endpoint group bound to ``ctx`` services."""
    router = APIRouter()
    app = ctx.app
    security_guard = ctx.security_guard
    context_engine = ctx.context_engine
    auth_enabled = ctx.auth_enabled

    # =========================================================================
    # =========================================================================
    # [AUDIT-01] SSE AUTHENTICATION: Short-lived, scoped stream tokens
    # =========================================================================

    @router.post("/api/v1/auth/sse-token")
    async def issue_sse_token(request: Request) -> dict[str, Any]:
        """Issue a short-lived (60s) SSE-scoped stream token for authenticated callers.
        The token may only be used to connect to /api/events/stream via stream_token query param.
        Long-lived API keys must NEVER be placed in URLs.
        """
        identity: Identity | None = (
            getattr(request.state, "identity", None) or TenantContext.get_current_identity()
        )
        if identity is None:
            raise HTTPException(
                status_code=401, detail="Authentication required to obtain an SSE stream token."
            )

        token, expires_at = security_guard.approval_service.create_token(
            tool_name="__sse_stream__",
            arguments={"scope": "sse_only", "tenant_id": identity.tenant_id},
            user_id=identity.user_id,
            execution_id="sse",
            ttl_seconds=60.0,
        )
        return {"stream_token": token, "expires_at": expires_at, "ttl_seconds": 60}

    # REAL-TIME SERVER-SENT EVENTS (SSE) ENDPOINT & STUDIO BROADCASTER
    # =========================================================================

    @router.get("/api/events/stream")
    @router.get("/events")
    async def sse_stream(
        request: Request = cast(Request, None),
        stream_token: str | None = Query(default=None),
    ) -> StreamingResponse:
        """Stream real-time system telemetry, DAG step updates, audit events, and governance changes.
        [AUDIT-01] Authenticate via short-lived stream_token (from POST /api/v1/auth/sse-token).
        EventSource cannot send custom headers; the stream_token query param is the scoped alternative.
        """
        identity: Identity | None = None
        if request is not None and hasattr(request, "state"):
            identity = getattr(request.state, "identity", None)
        if identity is None:
            identity = TenantContext.get_current_identity()

        # Validate stream_token when auth middleware is active and no session identity present
        if identity is None and stream_token:
            try:
                security_guard.approval_service.validate_and_consume(
                    token=stream_token,
                    tool_name="__sse_stream__",
                    arguments={"scope": "sse_only"},
                    user_id="anonymous",
                    execution_id="sse",
                )
            except Exception:
                raise HTTPException(status_code=401, detail="Invalid or expired SSE stream token.")
        elif identity is None and auth_enabled:
            raise HTTPException(
                status_code=401,
                detail="Authentication required. Obtain a stream token from POST /api/v1/auth/sse-token.",
            )

        sub_tenant_id = identity.tenant_id if identity else "default"
        sub_role = identity.role if identity else Role.VIEWER
        sub_user_id = identity.user_id if identity else "anonymous"

        async def event_generator() -> AsyncGenerator[str, None]:
            queue: asyncio.Queue[str] = asyncio.Queue()
            sub_record = {
                "queue": queue,
                "tenant_id": sub_tenant_id,
                "role": sub_role,
                "user_id": sub_user_id,
            }
            app.state.event_subscribers.append(sub_record)

            # Initial handshake event
            init_payload = json.dumps(
                {
                    "type": "handshake",
                    "status": "CONNECTED",
                    "timestamp": time.time(),
                    "server": "NexusAI-Studio",
                    "tenant_id": sub_tenant_id,
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
                            yield ": keepalive\n\n"
            except asyncio.CancelledError:
                pass
            finally:
                if sub_record in app.state.event_subscribers:
                    app.state.event_subscribers.remove(sub_record)

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
                "X-NexusAI-Mode": "simulation",
            },
        )

    return router
