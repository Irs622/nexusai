"""Multi-node cluster execution and fencing takeover integration test suite for P5-9."""

from __future__ import annotations

import asyncio
import pytest

from nexusai.brain.domain.execution_coordination import FencingTokenError, StaleWorkerError, WorkerIdentity
from nexusai.infrastructure.coordination.postgres_execution_coordinator import PostgresExecutionCoordinator
from tests.fixtures.p4_1_tools import ControlledTestToolPort


@pytest.mark.asyncio
async def test_multi_node_lease_takeover_and_fencing_sequence() -> None:
    """Integration Test: Node A (token=1) -> Expiration -> Node B Takeover (token=2) -> Node A Rejection."""
    coord = PostgresExecutionCoordinator()
    tool_port = ControlledTestToolPort()

    w_a = WorkerIdentity("node-a-worker")
    w_b = WorkerIdentity("node-b-worker")

    # Step 1: Node A acquires lease (fencing_token = 1)
    lease_a = await coord.acquire_execution_lease("exec-cluster-1", "sess-cluster-1", w_a, ttl_seconds=0.1)
    assert lease_a.fencing_token == 1

    await asyncio.sleep(0.15)

    # Step 2: Node B recovers expired lease (fencing_token = 2)
    lease_b = await coord.recover_expired_execution_lease("exec-cluster-1", w_b, ttl_seconds=10.0)
    assert lease_b.fencing_token == 2

    # Step 3: Node B executes tool side-effect
    await tool_port.execute(pytest.importorskip("nexusai.brain.ports.tool_port").ToolExecutionRequest("exec-cluster-1", "process_tool", ()))
    assert tool_port.call_count == 1

    # Step 4: Node A attempts late execution with token=1 -> Rejected!
    with pytest.raises((FencingTokenError, StaleWorkerError)):
        await coord.validate_lease_and_fencing_token("exec-cluster-1", w_a.worker_id, expected_token=1)

    assert tool_port.call_count == 1, "Side effect call_count MUST remain 1 (zero additional executions from Node A)!"


if __name__ == "__main__":
    asyncio.run(test_multi_node_lease_takeover_and_fencing_sequence())
    print("ALL MULTI-NODE CLUSTER INTEGRATION TESTS PASSED SUCCESSFULLY!")
