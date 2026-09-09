"""IGovernancePort protocol contract for admission control, capability verification, and resource reservation governance."""

from __future__ import annotations

from typing import Protocol

from nexusai.brain.domain.governance import (
    GovernanceDecision,
    GovernanceRequest,
    ResourceRequest,
    ResourceReservation,
    ResourceUsage,
)
from nexusai.brain.domain.human_approval import (
    HumanApprovalDecision,
    HumanApprovalRequest,
)


class IApprovalNotifierPort(Protocol):
    """Abstract port interface for dispatching outbound human safety approval notifications."""

    async def notify_approval_required(
        self,
        request: HumanApprovalRequest,
    ) -> bool:
        """Dispatch outbound notification that a high-risk tool action requires human approval.

        Args:
            request: The pending safety approval request domain model.

        Returns:
            True if notification was accepted or dispatched, False otherwise.
        """
        ...

    async def notify_approval_resolved(
        self,
        request: HumanApprovalRequest,
        decision: HumanApprovalDecision,
    ) -> bool:
        """Dispatch outbound notification that an approval request has been resolved.

        Args:
            request: The original safety approval request domain model.
            decision: The human operator decision payload.

        Returns:
            True if notification was accepted or dispatched, False otherwise.
        """
        ...


class IGovernancePort(Protocol):
    """Abstract port interface decoupling capability authorization and quota management from engine runtime."""

    async def authorize(self, request: GovernanceRequest) -> GovernanceDecision:
        """Evaluate capability authorization, token grant validity, and resource availability for a node execution."""
        ...

    async def reserve(
        self,
        execution_id: str,
        node_id: str,
        request: ResourceRequest,
    ) -> ResourceReservation | None:
        """Atomically reserve resources prior to execution. Returns None if quota exceeded."""
        ...

    async def release(self, reservation_id: str) -> bool:
        """Release an active resource reservation across all execution termination paths."""
        ...

    async def record_usage(self, reservation_id: str, usage: ResourceUsage) -> None:
        """Record actual resources consumed during execution prior to release."""
        ...
