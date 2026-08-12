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
