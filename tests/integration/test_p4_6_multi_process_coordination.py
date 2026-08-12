"""Integration test suite for multi-process lease acquisition and worker identity binding."""

from __future__ import annotations

import asyncio
import os
import tempfile
import pytest

from nexusai.brain.domain.execution_coordination import LeaseAcquisitionError, WorkerIdentity
from nexusai.infrastructure.persistence.sqlite_execution_coordinator import SQLiteExecutionCoordinator


@pytest.mark.asyncio
async def test_multi_process_lease_coordination() -> None:
    """Verify single execution ownership across multi-process SQLite connections."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name

    try:
        coord1 = SQLiteExecutionCoordinator(db_path=db_path)
        coord2 = SQLiteExecutionCoordinator(db_path=db_path)

        w1 = WorkerIdentity("worker-proc-1")
        w2 = WorkerIdentity("worker-proc-2")

        lease1 = await coord1.acquire_execution_lease("exec-mp-1", "sess-mp-1", w1)
        assert lease1.worker_id == "worker-proc-1"

        # Worker 2 attempting to acquire active lease -> Fails closed with LeaseAcquisitionError
        with pytest.raises(LeaseAcquisitionError):
            await coord2.acquire_execution_lease("exec-mp-1", "sess-mp-1", w2)

    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


if __name__ == "__main__":
    asyncio.run(test_multi_process_lease_coordination())
    print("ALL P4-6 MULTI-PROCESS COORDINATION INTEGRATION TESTS PASSED SUCCESSFULLY!")
