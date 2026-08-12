"""IApprovalStore protocol contract interface for durable approval persistence."""

from __future__ import annotations

from typing import Protocol, Sequence

from nexusai.brain.domain.human_approval import (
    ActionBinding,
    ApprovalGrant,
    HumanApprovalDecision,
    HumanApprovalRequest,
)


class IApprovalStore(Protocol):
    """Abstract port interface for durable persistence of safety approval requests, decisions, and single-use grants."""

    async def save_request(self, request: HumanApprovalRequest) -> HumanApprovalRequest:
        """Persist a new safety approval request in PENDING status."""
        ...

    async def get_request(self, approval_id: str) -> HumanApprovalRequest | None:
        """Retrieve approval request by approval_id."""
        ...

    async def record_decision(self, decision: HumanApprovalDecision) -> ApprovalGrant:
        """Atomically record operator decision (APPROVED or DENIED). Returns single-use ApprovalGrant if APPROVED."""
        ...

    async def verify_and_consume_grant(self, grant_id: str, expected_binding: ActionBinding) -> bool:
        """Atomically verify binding digest, expiration, and consume single-use grant in durable store."""
        ...

    async def get_grant(self, grant_id: str) -> ApprovalGrant | None:
        """Retrieve single-use approval grant by grant_id."""
        ...

    async def cancel_execution_requests(self, execution_id: str) -> int:
        """Cancel all pending requests bound to execution_id across processes."""
        ...
