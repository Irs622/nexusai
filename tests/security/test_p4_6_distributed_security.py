"""Security verification test suite for P4-6 Distributed Coordination invariants (P4-6-INV-01 to P4-6-INV-32)."""

from __future__ import annotations

import asyncio
import os
import tempfile
import time
import pytest

from nexusai.brain.domain.execution_coordination import (
    FencingTokenError,
    LeaseAcquisitionError,
    StaleWorkerError,
    WorkerIdentity,
)
from nexusai.infrastructure.persistence.sqlite_execution_coordinator import SQLiteExecutionCoordinator


@pytest.mark.asyncio
async def test_security_stale_fencing_token_execution_blocked() -> None:
    """Security Test (P4-6-INV-08 & P4-6-INV-09): Stale worker with obsolete fencing token cannot execute side effects."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name

    try:
        coord = SQLiteExecutionCoordinator(db_path=db_path)
        w_a = WorkerIdentity("worker-a")
        w_b = WorkerIdentity("worker-b")

        # Worker A acquires lease (fencing_token = 1)
        lease_a = await coord.acquire_execution_lease("exec-sec-1", "sess-sec-1", w_a, ttl_seconds=0.1)
        token_a = lease_a.fencing_token
        assert token_a == 1

        # Worker A pauses, lease expires
        await asyncio.sleep(0.15)

        # Worker B recovers expired lease (fencing_token = 2)
        lease_b = await coord.recover_expired_execution_lease("exec-sec-1", w_b, ttl_seconds=10.0)
        assert lease_b.fencing_token == 2

        # Worker A resumes and attempts execution using token_a (1) -> MUST FAIL CLOSED with FencingTokenError or StaleWorkerError!
        with pytest.raises((FencingTokenError, StaleWorkerError)):
            await coord.validate_lease_and_fencing_token("exec-sec-1", w_a.worker_id, expected_token=token_a)

    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


@pytest.mark.asyncio
async def test_security_stale_worker_cannot_release_current_lease() -> None:
    """Security Test (P4-6-INV-11): Stale worker cannot release another worker's active lease."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name

    try:
        coord = SQLiteExecutionCoordinator(db_path=db_path)
        w_a = WorkerIdentity("worker-a")
        w_b = WorkerIdentity("worker-b")

        lease_a = await coord.acquire_execution_lease("exec-sec-2", "sess-sec-2", w_a, ttl_seconds=0.1)
        await asyncio.sleep(0.15)

        lease_b = await coord.recover_expired_execution_lease("exec-sec-2", w_b, ttl_seconds=10.0)

        # Stale Worker A attempts releasing Worker B's lease -> MUST FAIL with StaleWorkerError!
        with pytest.raises(StaleWorkerError):
            await coord.release_execution_lease(lease_b.lease_id, w_a)

    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


if __name__ == "__main__":
    asyncio.run(test_security_stale_fencing_token_execution_blocked())
    asyncio.run(test_security_stale_worker_cannot_release_current_lease())
    print("ALL P4-6 DISTRIBUTED SECURITY TESTS PASSED SUCCESSFULLY!")
