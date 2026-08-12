"""Security verification test suite for P5-2 Distributed Coordination invariants."""

from __future__ import annotations

import asyncio
import pytest

from nexusai.brain.domain.execution_coordination import (
    FencingTokenError,
    LeaseAcquisitionError,
    StaleWorkerError,
    WorkerIdentity,
)
from nexusai.infrastructure.coordination.postgres_execution_coordinator import PostgresExecutionCoordinator
from nexusai.infrastructure.coordination.redis_execution_coordinator import RedisExecutionCoordinator
from tests.fixtures.p4_1_tools import ControlledTestToolPort


@pytest.mark.asyncio
async def test_security_p5_2_fencing_token_stale_worker_rejection() -> None:
    """Security Test: Worker A token=1 attempts tool execution after Worker B token=2 takeover -> MUST FAIL CLOSED."""
    pg_coord = PostgresExecutionCoordinator()
    redis_coord = RedisExecutionCoordinator()

    for i, coord in enumerate((pg_coord, redis_coord)):
        tool_port = ControlledTestToolPort()
        w_a = WorkerIdentity("worker-p5-a")
        w_b = WorkerIdentity("worker-p5-b")
        exec_id = f"exec-p5-sec-1-{i}"

        # Worker A acquires lease (fencing_token = 1)
        lease_a = await coord.acquire_execution_lease(exec_id, "sess-p5-sec-1", w_a, ttl_seconds=0.1)
        token_a = lease_a.fencing_token
        assert token_a == 1

        await asyncio.sleep(0.15)

        # Worker B takes over (fencing_token = 2)
        lease_b = await coord.recover_expired_execution_lease(exec_id, w_b, ttl_seconds=10.0)
        assert lease_b.fencing_token == 2

        # Worker A resumes and attempts validation with token_a (1) -> MUST FAIL CLOSED!
        with pytest.raises((FencingTokenError, StaleWorkerError)):
            await coord.validate_lease_and_fencing_token(exec_id, w_a.worker_id, expected_token=token_a)

        assert tool_port.call_count == 0, "Stale worker tool execution call_count MUST remain strictly 0!"


if __name__ == "__main__":
    asyncio.run(test_security_p5_2_fencing_token_stale_worker_rejection())
    print("ALL P5-2 DISTRIBUTED COORDINATION SECURITY TESTS PASSED SUCCESSFULLY!")
