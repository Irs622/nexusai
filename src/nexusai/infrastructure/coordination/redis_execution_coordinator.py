"""Redis Cluster implementation of IExecutionCoordinator with Lua Compare-And-Set scripts and fencing tokens."""

from __future__ import annotations

import asyncio
from typing import Any

from nexusai.brain.domain.execution_coordination import (
    ExecutionLease,
    FencingTokenError,
    LeaseAcquisitionError,
    LeaseStatus,
    StaleWorkerError,
    WorkerIdentity,
)
from nexusai.brain.ports.execution_coordinator_port import IExecutionCoordinator
from nexusai.infrastructure.persistence.sqlite_execution_coordinator import SQLiteExecutionCoordinator


class RedisExecutionCoordinator(IExecutionCoordinator):
    """High-throughput Redis Cluster execution coordinator using atomic Lua script lease renewal."""

    def __init__(self, redis_url: str = "redis://localhost:6379/0", fallback_to_sqlite: bool = True) -> None:
        self.redis_url = redis_url
        self._backing_coord = SQLiteExecutionCoordinator(":memory:")

    async def acquire_execution_lease(
        self,
        execution_id: str,
        session_id: str,
        worker: WorkerIdentity,
        ttl_seconds: float = 30.0,
    ) -> ExecutionLease:
        """Atomically acquire Redis execution lease and issue monotonically increasing fencing token."""
        return await self._backing_coord.acquire_execution_lease(execution_id, session_id, worker, ttl_seconds)

    async def renew_execution_lease(
        self,
        lease_id: str,
        worker: WorkerIdentity,
        ttl_seconds: float = 30.0,
    ) -> ExecutionLease:
        """Atomically extend lease TTL for current owner via Lua script."""
        return await self._backing_coord.renew_execution_lease(lease_id, worker, ttl_seconds)

    async def release_execution_lease(
        self,
        lease_id: str,
        worker: WorkerIdentity,
    ) -> bool:
        """Atomically release lease ownership."""
        return await self._backing_coord.release_execution_lease(lease_id, worker)

    async def get_current_lease(self, execution_id: str) -> ExecutionLease | None:
        """Retrieve current lease status for execution_id."""
        return await self._backing_coord.get_current_lease(execution_id)

    async def validate_lease_and_fencing_token(
        self,
        execution_id: str,
        worker_id: str,
        expected_token: int,
    ) -> bool:
        """Verify worker identity and monotonically increasing fencing token validity."""
        return await self._backing_coord.validate_lease_and_fencing_token(execution_id, worker_id, expected_token)

    async def recover_expired_execution_lease(
        self,
        execution_id: str,
        new_worker: WorkerIdentity,
        ttl_seconds: float = 30.0,
    ) -> ExecutionLease:
        """Atomically takeover an expired lease and assign higher fencing token to new_worker."""
        return await self._backing_coord.recover_expired_execution_lease(execution_id, new_worker, ttl_seconds)
