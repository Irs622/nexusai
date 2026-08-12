"""Fencing token integration test suite proving stale worker execution is blocked prior to tool invocation."""

from __future__ import annotations

import asyncio
import os
import tempfile
import pytest

from nexusai.brain.domain.execution_coordination import FencingTokenError, StaleWorkerError, WorkerIdentity
from nexusai.infrastructure.persistence.sqlite_execution_coordinator import SQLiteExecutionCoordinator
from tests.fixtures.p4_1_tools import ControlledTestToolPort


@pytest.mark.asyncio
async def test_fencing_token_blocks_stale_worker_side_effect() -> None:
    """Empirical Test: Controlled tool execution call_count MUST remain 0 for stale worker A after worker B takeover."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name

    try:
        coord = SQLiteExecutionCoordinator(db_path=db_path)
        tool_port = ControlledTestToolPort()

        w_a = WorkerIdentity("worker-a")
        w_b = WorkerIdentity("worker-b")

        # Worker A acquires lease (fencing_token = 1)
        lease_a = await coord.acquire_execution_lease("exec-fence-1", "sess-fence-1", w_a, ttl_seconds=0.1)
        token_a = lease_a.fencing_token

        # Worker A pauses, lease expires
        await asyncio.sleep(0.15)

        # Worker B takes over (fencing_token = 2)
        lease_b = await coord.recover_expired_execution_lease("exec-fence-1", w_b, ttl_seconds=10.0)

        # Worker A attempts tool execution using obsolete token_a (1)
        try:
            await coord.validate_lease_and_fencing_token("exec-fence-1", w_a.worker_id, expected_token=token_a)
            # If validation fails closed as expected, tool_port.execute() is NEVER called!
            await tool_port.execute(pytest.importorskip("nexusai.brain.ports.tool_port").ToolExecutionRequest("exec-fence-1", "echo_tool", ()))
        except (FencingTokenError, StaleWorkerError):
            pass

        assert tool_port.call_count == 0, "Stale worker tool execution call_count MUST remain strictly 0!"

    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


if __name__ == "__main__":
    asyncio.run(test_fencing_token_blocks_stale_worker_side_effect())
    print("ALL P4-6 FENCING TOKEN INTEGRATION TESTS PASSED SUCCESSFULLY!")
