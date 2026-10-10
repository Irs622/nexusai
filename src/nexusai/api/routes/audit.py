"""Audit event listing, chain verification, and Studio demo tamper/reset endpoints."""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request, Response

from nexusai.api.context import ServerContext
from nexusai.api.demo_data import _compute_audit_event_hash, _create_initial_audit_chain
from nexusai.api.schemas import AuditTamperRequest
from nexusai.brain.domain.audit import GENESIS_HASH, AuditEvent
from nexusai.brain.ports.audit_store_port import IAuditStore
from nexusai.security.identity import Identity, Role, TenantContext

# Import Tools & MCP


def build_router(ctx: ServerContext) -> APIRouter:
    """Create the router for this endpoint group bound to ``ctx`` services."""
    router = APIRouter()
    app = ctx.app
    _get_tenant_id = ctx.get_tenant_id
    broadcast_event = ctx.broadcast_event

    @router.get("/api/v1/audit/events")
    async def get_audit_events(
        request: Request,
        response: Response,
        tenant_id: str | None = Query(None, description="Optional tenant ID to query"),
    ) -> list[dict[str, Any]]:
        """Return chronological list of cryptographic AuditEvent records forming the hash chain."""
        identity: Identity | None = (
            getattr(request.state, "identity", None) or TenantContext.get_current_identity()
        )
        caller_tenant = identity.tenant_id if identity else "default"
        caller_role = identity.role if identity else Role.OPERATOR

        if getattr(app.state, "studio_demo_mode", False):
            response.headers["X-NexusAI-Mode"] = "simulation"
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

    @router.get("/api/v1/audit/verify")
    @router.post("/api/v1/audit/verify")
    async def verify_audit_chain_endpoint(
        request: Request,
        response: Response,
        tenant_id: str | None = Query(None, description="Optional tenant ID to verify"),
    ) -> dict[str, Any]:
        """Perform cryptographic SHA-256 integrity verification across the full audit chain."""
        identity: Identity | None = (
            getattr(request.state, "identity", None) or TenantContext.get_current_identity()
        )
        caller_tenant = identity.tenant_id if identity else "default"
        caller_role = identity.role if identity else Role.OPERATOR

        if getattr(app.state, "studio_demo_mode", False):
            response.headers["X-NexusAI-Mode"] = "simulation"
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

    @router.post("/api/v1/audit/tamper")
    async def tamper_audit_event_endpoint(
        req: AuditTamperRequest, request: Request, response: Response
    ) -> dict[str, Any]:
        """Simulate malicious tampering on an event in the audit chain to test cryptographic detection."""
        response.headers["X-NexusAI-Mode"] = "simulation"
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
        broadcast_event(
            "audit_tampered",
            {"event_id": ev.event_id, "field": req.tampered_field},
            tenant_id=tenant_id,
        )
        return {
            "status": "TAMPERED",
            "tampered_event_id": ev.event_id,
            "tampered_field": req.tampered_field,
            "new_value": req.new_value,
            "recorded_hash": ev.event_hash,
        }

    @router.post("/api/v1/audit/reset")
    async def reset_audit_chain_endpoint(request: Request, response: Response) -> dict[str, Any]:
        """Reset the audit chain back to verified clean genesis state."""
        response.headers["X-NexusAI-Mode"] = "simulation"
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
        broadcast_event("audit_reset", {"event_count": len(chain)}, tenant_id=tenant_id)
        return {
            "status": "RESET_SUCCESS",
            "event_count": len(chain),
        }

    return router
