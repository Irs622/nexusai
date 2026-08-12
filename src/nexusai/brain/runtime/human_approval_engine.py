"""HumanApprovalEngine runtime implementation for governed Human-in-the-Loop safety approval workflows."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from nexusai.brain.domain.human_approval import (
    ActionBinding,
    ApprovalCancelledError,
    ApprovalError,
    ApprovalExpiredError,
    ApprovalGrant,
    ApprovalMismatchError,
    ApprovalReplayError,
    ApprovalStatus,
    HumanApprovalDecision,
    HumanApprovalRequest,
)
from nexusai.brain.domain.observability import RuntimeEvent, RuntimeEventType
from nexusai.brain.ports.approval_store_port import IApprovalStore
from nexusai.brain.ports.human_approval_port import IHumanApprovalPort
from nexusai.brain.ports.observability_port import IObservabilityPort


class HumanApprovalEngine(IHumanApprovalPort):
    """Thread and coroutine safe Human-in-the-Loop safety approval engine supporting both host-local and durable SQLite persistence."""

    def __init__(
        self,
        default_ttl_seconds: float = 600.0,
        telemetry: IObservabilityPort | None = None,
        store: IApprovalStore | None = None,
    ) -> None:
        self.default_ttl_seconds = default_ttl_seconds
        self.telemetry = telemetry
        self.store = store
        self._lock = asyncio.Lock()

        self._requests: dict[str, HumanApprovalRequest] = {}
        self._grants: dict[str, ApprovalGrant] = {}

    async def _safe_telemetry_event(
        self,
        event_type: RuntimeEventType,
        approval_id: str,
        attributes: dict[str, Any] | None = None,
    ) -> None:
        if not self.telemetry:
            return
        try:
            now = time.time()
            evt = RuntimeEvent(
                event_id=f"app-evt-{int(now * 1000)}",
                event_type=event_type,
                timestamp=now,
                attributes={"approval_id": approval_id, **(attributes or {})},
            )
            await self.telemetry.emit_event(evt)
        except Exception:
            pass

    async def request_approval(
        self,
        request: HumanApprovalRequest,
    ) -> HumanApprovalRequest:
        """Submit a safety approval request for human operator review."""
        if self.store is not None:
            res = await self.store.save_request(request)
            await self._safe_telemetry_event(
                RuntimeEventType.EXECUTION_STARTED,
                approval_id=request.approval_id,
                attributes={"risk_level": request.risk_level.value, "tool_id": request.binding.tool_id},
            )
            return res

        async with self._lock:
            if request.approval_id in self._requests:
                raise ValueError(f"Approval request '{request.approval_id}' is already registered")

            now = time.time()
            expires = request.expires_at or (now + self.default_ttl_seconds)

            stored_req = HumanApprovalRequest(
                approval_id=request.approval_id,
                binding=request.binding,
                risk_level=request.risk_level,
                prompt_summary=request.prompt_summary,
                status=ApprovalStatus.PENDING,
                created_at=now,
                expires_at=expires,
                metadata=request.metadata,
            )
            self._requests[request.approval_id] = stored_req

        await self._safe_telemetry_event(
            RuntimeEventType.EXECUTION_STARTED,
            approval_id=request.approval_id,
            attributes={"risk_level": request.risk_level.value, "tool_id": request.binding.tool_id},
        )
        return stored_req

    async def submit_decision(
        self,
        decision: HumanApprovalDecision,
    ) -> ApprovalGrant:
        """Submit an operator decision (APPROVE or DENY). Returns single-use ApprovalGrant."""
        if self.store is not None:
            return await self.store.record_decision(decision)

        async with self._lock:
            req = self._requests.get(decision.approval_id)
            if req is None:
                raise ValueError(f"Approval request '{decision.approval_id}' not found")

            # Atomic State Transition Invariant (INV-HA-06)
            if req.status != ApprovalStatus.PENDING:
                raise ValueError(
                    f"Cannot submit decision for request '{decision.approval_id}' in status '{req.status.value}'"
                )

            now = time.time()

            # Defense-in-depth expiration check
            if req.expires_at and now >= req.expires_at:
                updated_req = HumanApprovalRequest(
                    approval_id=req.approval_id,
                    binding=req.binding,
                    risk_level=req.risk_level,
                    prompt_summary=req.prompt_summary,
                    status=ApprovalStatus.EXPIRED,
                    created_at=req.created_at,
                    expires_at=req.expires_at,
                    metadata=req.metadata,
                )
                self._requests[req.approval_id] = updated_req
                raise ApprovalExpiredError(f"Approval request '{decision.approval_id}' has expired")

            if decision.status == ApprovalStatus.DENIED:
                updated_req = HumanApprovalRequest(
                    approval_id=req.approval_id,
                    binding=req.binding,
                    risk_level=req.risk_level,
                    prompt_summary=req.prompt_summary,
                    status=ApprovalStatus.DENIED,
                    created_at=req.created_at,
                    expires_at=req.expires_at,
                    metadata=req.metadata,
                )
                self._requests[req.approval_id] = updated_req
                raise ApprovalMismatchError(f"Human operator denied request '{decision.approval_id}': {decision.reason}")

            # Operator APPROVED -> Issue single-use ApprovalGrant
            updated_req = HumanApprovalRequest(
                approval_id=req.approval_id,
                binding=req.binding,
                risk_level=req.risk_level,
                prompt_summary=req.prompt_summary,
                status=ApprovalStatus.APPROVED,
                created_at=req.created_at,
                expires_at=req.expires_at,
                metadata=req.metadata,
            )
            self._requests[req.approval_id] = updated_req

            grant_id = f"grant-{req.approval_id}"
            grant = ApprovalGrant(
                grant_id=grant_id,
                approval_id=req.approval_id,
                binding=req.binding,
                issued_at=now,
                expires_at=req.expires_at or (now + 600.0),
                actor=decision.actor,
            )
            self._grants[grant_id] = grant
            return grant

    async def verify_and_consume_grant(
        self,
        grant_id: str,
        expected_binding: ActionBinding,
    ) -> bool:
        """Verify action binding and single-use grant validity, then atomically consume grant to prevent replay."""
        if self.store is not None:
            return await self.store.verify_and_consume_grant(grant_id, expected_binding)

        async with self._lock:
            grant = self._grants.get(grant_id)
            if grant is None:
                raise ApprovalMismatchError(f"Approval grant '{grant_id}' not found")

            # INV-HA-08: Single-Use Replay Protection
            if grant.consumed_at is not None:
                raise ApprovalReplayError(f"Approval grant '{grant_id}' has already been consumed at {grant.consumed_at}")

            # INV-HA-04: Expiration Defense-in-Depth
            now = time.time()
            if now >= grant.expires_at:
                raise ApprovalExpiredError(f"Approval grant '{grant_id}' has expired")

            # INV-HA-01 & INV-HA-02: Action Digest & Plan Fingerprint Match Verification
            if grant.binding.action_digest != expected_binding.action_digest:
                raise ApprovalMismatchError(
                    f"Action binding mismatch: grant digest '{grant.binding.action_digest}' != expected digest '{expected_binding.action_digest}'"
                )

            # Atomically mark consumed
            consumed_grant = ApprovalGrant(
                grant_id=grant.grant_id,
                approval_id=grant.approval_id,
                binding=grant.binding,
                issued_at=grant.issued_at,
                expires_at=grant.expires_at,
                actor=grant.actor,
                consumed_at=now,
            )
            self._grants[grant_id] = consumed_grant

            req = self._requests.get(grant.approval_id)
            if req:
                self._requests[grant.approval_id] = HumanApprovalRequest(
                    approval_id=req.approval_id,
                    binding=req.binding,
                    risk_level=req.risk_level,
                    prompt_summary=req.prompt_summary,
                    status=ApprovalStatus.CONSUMED,
                    created_at=req.created_at,
                    expires_at=req.expires_at,
                    metadata=req.metadata,
                )

            return True

    async def cancel_pending_requests(self, execution_id: str) -> int:
        """Cancel all pending approval requests bound to an interrupted or cancelled execution."""
        if self.store is not None:
            return await self.store.cancel_execution_requests(execution_id)

        async with self._lock:
            cancelled_cnt = 0
            for app_id, req in list(self._requests.items()):
                if req.binding.execution_id == execution_id and req.status == ApprovalStatus.PENDING:
                    self._requests[app_id] = HumanApprovalRequest(
                        approval_id=req.approval_id,
                        binding=req.binding,
                        risk_level=req.risk_level,
                        prompt_summary=req.prompt_summary,
                        status=ApprovalStatus.CANCELLED,
                        created_at=req.created_at,
                        expires_at=req.expires_at,
                        metadata=req.metadata,
                    )
                    cancelled_cnt += 1
            return cancelled_cnt

    async def get_request(self, approval_id: str) -> HumanApprovalRequest | None:
        """Retrieve approval request state by approval_id."""
        if self.store is not None:
            return await self.store.get_request(approval_id)

        async with self._lock:
            return self._requests.get(approval_id)
