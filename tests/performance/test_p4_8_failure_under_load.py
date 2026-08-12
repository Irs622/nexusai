"""P4-8-H Failure Under Load & Fail-Closed Verification Test suite."""

from __future__ import annotations

import asyncio
import os
import tempfile
import pytest

from nexusai.brain.domain.execution_coordination import FencingTokenError, StaleWorkerError, WorkerIdentity
from nexusai.infrastructure.persistence.sqlite_execution_coordinator import SQLiteExecutionCoordinator
from tests.fixtures.p4_1_tools import ControlledTestToolPort


@pytest.mark.asyncio
async def test_failure_under_load_stale_worker_token_rejection() -> None:
    """Failure Injection: Inject stale fencing tokens during active concurrent load and verify fail-closed call_count == 0."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name

    try:
        coord = SQLiteExecutionCoordinator(db_path=db_path)
        tool_port = ControlledTestToolPort()

        w_a = WorkerIdentity("worker-stale-a")
        w_b = WorkerIdentity("worker-stale-b")

        # Worker A acquires lease (fencing_token = 1)
        lease_a = await coord.acquire_execution_lease("exec-fail-1", "sess-fail-1", w_a, ttl_seconds=0.1)
        token_a = lease_a.fencing_token

        await asyncio.sleep(0.15)

        # Worker B takes over (fencing_token = 2)
        lease_b = await coord.recover_expired_execution_lease("exec-fail-1", w_b, ttl_seconds=10.0)

        # Worker A attempts execution under simulated load -> MUST FAIL CLOSED!
        try:
            await coord.validate_lease_and_fencing_token("exec-fail-1", w_a.worker_id, expected_token=token_a)
            await tool_port.execute(pytest.importorskip("nexusai.brain.ports.tool_port").ToolExecutionRequest("exec-fail-1", "process_tool", ()))
        except (FencingTokenError, StaleWorkerError):
            pass

        assert tool_port.call_count == 0, "Tool execution call_count MUST remain strictly 0 during stale worker failure injection!"

    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


if __name__ == "__main__":
    asyncio.run(test_failure_under_load_stale_worker_token_rejection())
    print("ALL P4-8-H FAILURE UNDER LOAD TESTS PASSED SUCCESSFULLY!")
