"""IExecutionCoordinator protocol contract interface for distributed execution ownership, leases, and fencing tokens."""

from __future__ import annotations

from typing import Protocol

from nexusai.brain.domain.execution_coordination import ExecutionLease, WorkerIdentity


class IExecutionCoordinator(Protocol):
    """Abstract protocol port interface for distributed execution ownership, lease management, and fencing token validation."""

    async def acquire_execution_lease(
        self,
        execution_id: str,
        session_id: str,
        worker: WorkerIdentity,
        ttl_seconds: float = 30.0,
    ) -> ExecutionLease:
        """Atomically acquire time-bounded execution lease and issue monotonically increasing fencing token."""
        ...

    async def renew_execution_lease(
        self,
        lease_id: str,
        worker: WorkerIdentity,
        ttl_seconds: float = 30.0,
    ) -> ExecutionLease:
        """Atomically extend lease TTL for current owner."""
        ...

    async def release_execution_lease(
        self,
        lease_id: str,
        worker: WorkerIdentity,
    ) -> bool:
        """Atomically release lease ownership."""
        ...

    async def get_current_lease(
        self,
        execution_id: str,
    ) -> ExecutionLease | None:
        """Retrieve current lease status for execution_id."""
        ...

    async def validate_lease_and_fencing_token(
        self,
        execution_id: str,
        worker_id: str,
        expected_token: int,
    ) -> bool:
        """Verify worker identity and monotonically increasing fencing token validity prior to side-effect execution."""
        ...

    async def recover_expired_execution_lease(
        self,
        execution_id: str,
        new_worker: WorkerIdentity,
        ttl_seconds: float = 30.0,
    ) -> ExecutionLease:
        """Atomically takeover an expired lease, issue a higher fencing token, and assign to new_worker."""
        ...
