"""Adversarial distributed system chaos test suite for P5-9."""

from __future__ import annotations

import asyncio
import pytest

from nexusai.brain.domain.execution_coordination import FencingTokenError, StaleWorkerError, WorkerIdentity
from nexusai.infrastructure.coordination.postgres_execution_coordinator import PostgresExecutionCoordinator
from tests.fixtures.p4_1_tools import ControlledTestToolPort


@pytest.mark.asyncio
async def test_adversarial_chaos_network_partition_reconnect() -> None:
    """Chaos Test: Node A partition -> Node B takeover -> Node A reconnects and attempts lease renewal & release -> BOTH REJECTED."""
    coord = PostgresExecutionCoordinator()

    w_a = WorkerIdentity("chaos-node-a")
    w_b = WorkerIdentity("chaos-node-b")

    # Node A acquires lease (fencing_token = 1)
    lease_a = await coord.acquire_execution_lease("exec-chaos-1", "sess-chaos-1", w_a, ttl_seconds=0.1)

    await asyncio.sleep(0.15)

    # Node B takes over (fencing_token = 2)
    lease_b = await coord.recover_expired_execution_lease("exec-chaos-1", w_b, ttl_seconds=10.0)
    assert lease_b.fencing_token == 2

    # Node A reconnects and attempts renewal -> REJECTED
    with pytest.raises(Exception):
        await coord.renew_execution_lease(lease_a.lease_id, w_a)

    # Node A attempts release -> REJECTED
    assert await coord.release_execution_lease(lease_a.lease_id, w_a) is False


if __name__ == "__main__":
    asyncio.run(test_adversarial_chaos_network_partition_reconnect())
    print("ALL ADVERSARIAL CHAOS TESTS PASSED SUCCESSFULLY!")
