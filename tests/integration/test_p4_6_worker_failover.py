"""Worker failover integration test suite for P4-6 Distributed Coordination."""

from __future__ import annotations

import asyncio
import os
import tempfile
import pytest

from nexusai.brain.domain.execution_coordination import LeaseStatus, WorkerIdentity
from nexusai.infrastructure.persistence.sqlite_execution_coordinator import SQLiteExecutionCoordinator


@pytest.mark.asyncio
async def test_worker_failover_on_lease_expiration() -> None:
    """Verify Worker B takeover after Worker A lease expiration with fencing token increment."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name

    try:
        coord = SQLiteExecutionCoordinator(db_path=db_path)
        w_a = WorkerIdentity("worker-a")
        w_b = WorkerIdentity("worker-b")

        lease_a = await coord.acquire_execution_lease("exec-fo-1", "sess-fo-1", w_a, ttl_seconds=0.1)
        assert lease_a.fencing_token == 1

        # Wait for Worker A lease to expire
        await asyncio.sleep(0.15)

        # Worker B recovers expired lease
        lease_b = await coord.recover_expired_execution_lease("exec-fo-1", w_b, ttl_seconds=10.0)
        assert lease_b.worker_id == "worker-b"
        assert lease_b.fencing_token == 2
        assert lease_b.status == LeaseStatus.LEASED

    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


if __name__ == "__main__":
    asyncio.run(test_worker_failover_on_lease_expiration())
    print("ALL P4-6 WORKER FAILOVER TESTS PASSED SUCCESSFULLY!")
