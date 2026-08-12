"""Reusable domain contract test suite for IExecutionCoordinator adapters (SQLite, PostgreSQL, and Redis)."""

from __future__ import annotations

import asyncio
import os
import tempfile
import pytest

from nexusai.brain.domain.execution_coordination import (
    FencingTokenError,
    LeaseAcquisitionError,
    LeaseStatus,
    StaleWorkerError,
    WorkerIdentity,
)
from nexusai.brain.ports.execution_coordinator_port import IExecutionCoordinator
from nexusai.infrastructure.persistence.sqlite_execution_coordinator import SQLiteExecutionCoordinator


async def verify_coordinator_contract(coord: IExecutionCoordinator) -> None:
    """Run full compliance test suite against any IExecutionCoordinator implementation."""
    w1 = WorkerIdentity("worker-contract-1")
    w2 = WorkerIdentity("worker-contract-2")

    exec_id = "exec-contract-1"
    sess_id = "sess-contract-1"

    # 1. Acquire lease -> fencing_token = 1
    lease1 = await coord.acquire_execution_lease(exec_id, sess_id, w1, ttl_seconds=0.1)
    assert lease1.worker_id == "worker-contract-1"
    assert lease1.fencing_token == 1

    # 2. Worker 2 attempts acquisition while lease is active -> Must fail!
    with pytest.raises(LeaseAcquisitionError):
        await coord.acquire_execution_lease(exec_id, sess_id, w2, ttl_seconds=10.0)

    # 3. Wait for lease TTL to expire
    await asyncio.sleep(0.15)

    # 4. Worker 2 recovers expired lease -> fencing_token = 2
    lease2 = await coord.recover_expired_execution_lease(exec_id, w2, ttl_seconds=10.0)
    assert lease2.worker_id == "worker-contract-2"
    assert lease2.fencing_token == 2

    # 5. Worker 1 resumes and attempts execution with obsolete token 1 -> Must fail closed!
    with pytest.raises((FencingTokenError, StaleWorkerError)):
        await coord.validate_lease_and_fencing_token(exec_id, w1.worker_id, expected_token=1)

    # 6. Worker 2 validates active token 2 -> Must succeed!
    assert await coord.validate_lease_and_fencing_token(exec_id, w2.worker_id, expected_token=2) is True

    # 7. Worker 2 releases lease
    assert await coord.release_execution_lease(lease2.lease_id, w2) is True


@pytest.mark.asyncio
async def test_sqlite_coordinator_conformance() -> None:
    """Test SQLiteExecutionCoordinator conformance to IExecutionCoordinator contract."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name

    try:
        coord = SQLiteExecutionCoordinator(db_path=db_path)
        await verify_coordinator_contract(coord)
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


if __name__ == "__main__":
    asyncio.run(test_sqlite_coordinator_conformance())
    print("ALL COORDINATOR CONTRACT CONFORMANCE TESTS PASSED SUCCESSFULLY!")
