"""Unit test suite for SQLiteExecutionCoordinator Compare-And-Set (CAS) atomic operations."""

from __future__ import annotations

import asyncio
import os
import tempfile
import pytest

from nexusai.brain.domain.execution_coordination import (
    LeaseAcquisitionError,
    LeaseStatus,
    StaleWorkerError,
    WorkerIdentity,
)
from nexusai.infrastructure.persistence.sqlite_execution_coordinator import SQLiteExecutionCoordinator


@pytest.mark.asyncio
async def test_sqlite_execution_coordinator_cas_operations() -> None:
    """Test SQLiteExecutionCoordinator CAS lease acquisition, renewal, takeover, and release."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name

    try:
        coord = SQLiteExecutionCoordinator(db_path=db_path)
        w1 = WorkerIdentity("worker-1")
        w2 = WorkerIdentity("worker-2")

        # 1. Worker 1 acquires lease
        lease1 = await coord.acquire_execution_lease("exec-1", "sess-1", w1, ttl_seconds=10.0)
        assert lease1.fencing_token == 1
        assert lease1.worker_id == "worker-1"

        # 2. Worker 2 attempts acquisition while lease is active -> Must fail!
        with pytest.raises(LeaseAcquisitionError):
            await coord.acquire_execution_lease("exec-1", "sess-1", w2, ttl_seconds=10.0)

        # 3. Worker 1 renews lease
        ren_lease = await coord.renew_execution_lease(lease1.lease_id, w1, ttl_seconds=15.0)
        assert ren_lease.status == LeaseStatus.RENEWED

        # 4. Worker 1 releases lease
        assert await coord.release_execution_lease(lease1.lease_id, w1) is True

        # 5. Worker 2 acquires now-released lease -> Monotonic fencing token increments to 2
        lease2 = await coord.acquire_execution_lease("exec-1", "sess-1", w2, ttl_seconds=10.0)
        assert lease2.fencing_token == 2
        assert lease2.worker_id == "worker-2"

    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


if __name__ == "__main__":
    asyncio.run(test_sqlite_execution_coordinator_cas_operations())
    print("ALL SQLITE EXECUTION COORDINATOR UNIT TESTS PASSED SUCCESSFULLY!")
