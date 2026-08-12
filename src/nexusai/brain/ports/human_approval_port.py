"""IHumanApprovalPort protocol contract interface for managing Human-in-the-Loop safety approval workflows."""

from __future__ import annotations

from typing import Protocol

from nexusai.brain.domain.human_approval import (
    ActionBinding,
    ApprovalGrant,
    HumanApprovalDecision,
    HumanApprovalRequest,
)


class IHumanApprovalPort(Protocol):
    """Abstract port interface decoupling Human Safety Approval requests and single-use grant verification from execution engines."""

    async def request_approval(
        self,
        request: HumanApprovalRequest,
    ) -> HumanApprovalRequest:
        """Submit a safety approval request for human operator review."""
        ...

    async def submit_decision(
        self,
        decision: HumanApprovalDecision,
    ) -> ApprovalGrant:
        """Submit an operator decision (APPROVE or DENY) for a pending approval request. Returns single-use ApprovalGrant."""
        ...

    async def verify_and_consume_grant(
        self,
        grant_id: str,
        expected_binding: ActionBinding,
    ) -> bool:
        """Verify action binding and single-use grant validity, then atomically consume grant to prevent replay."""
        ...

    async def cancel_pending_requests(self, execution_id: str) -> int:
        """Cancel all pending approval requests bound to an interrupted or cancelled execution."""
        ...

    async def get_request(self, approval_id: str) -> HumanApprovalRequest | None:
        """Retrieve approval request state by approval_id."""
        ...
