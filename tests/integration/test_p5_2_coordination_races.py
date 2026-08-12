"""Adversarial race test suite for P5-2 Distributed Coordination with network pause & fencing boundary verification."""

from __future__ import annotations

import asyncio
import pytest

from nexusai.brain.domain.execution_coordination import FencingTokenError, StaleWorkerError, WorkerIdentity
from nexusai.infrastructure.coordination.postgres_execution_coordinator import PostgresExecutionCoordinator
from tests.fixtures.p4_1_tools import ControlledTestToolPort


@pytest.mark.asyncio
async def test_p5_2_network_pause_fencing_race_verification() -> None:
    """Race Test: Worker A validates token=1 -> network pause -> Worker B takeover token=2 -> Worker A side-effect boundary check fails closed."""
    coord = PostgresExecutionCoordinator()
    tool_port = ControlledTestToolPort()

    w_a = WorkerIdentity("worker-p5-race-a")
    w_b = WorkerIdentity("worker-p5-race-b")

    # Worker A acquires lease (fencing_token = 1)
    lease_a = await coord.acquire_execution_lease("exec-race-p5", "sess-race-p5", w_a, ttl_seconds=0.1)
    token_a = lease_a.fencing_token

    # Simulate network pause for Worker A while lease expires
    await asyncio.sleep(0.15)

    # Worker B takes over (fencing_token = 2)
    lease_b = await coord.recover_expired_execution_lease("exec-race-p5", w_b, ttl_seconds=10.0)
    assert lease_b.fencing_token == 2

    # Worker A resumes from network pause and attempts tool execution boundary check
    side_effect_executed = False
    try:
        # ExecutionEngine validates fencing token immediately prior to IToolPort dispatch
        if await coord.validate_lease_and_fencing_token("exec-race-p5", w_a.worker_id, expected_token=token_a):
            await tool_port.execute(pytest.importorskip("nexusai.brain.ports.tool_port").ToolExecutionRequest("exec-race-p5", "process_tool", ()))
            side_effect_executed = True
    except (FencingTokenError, StaleWorkerError):
        pass

    assert side_effect_executed is False
    assert tool_port.call_count == 0, "Stale worker tool execution call_count MUST remain strictly 0!"


if __name__ == "__main__":
    asyncio.run(test_p5_2_network_pause_fencing_race_verification())
    print("ALL P5-2 COORDINATION RACE TESTS PASSED SUCCESSFULLY!")
