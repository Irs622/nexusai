"""RedisExecutionCoordinator contract conformance integration test suite."""

from __future__ import annotations

import asyncio
import pytest

from nexusai.infrastructure.coordination.redis_execution_coordinator import RedisExecutionCoordinator
from tests.contracts.test_execution_coordinator_contract import verify_coordinator_contract


@pytest.mark.asyncio
async def test_redis_coordinator_conformance() -> None:
    """Verify RedisExecutionCoordinator satisfies full IExecutionCoordinator domain contract."""
    coord = RedisExecutionCoordinator()
    await verify_coordinator_contract(coord)


if __name__ == "__main__":
    asyncio.run(test_redis_coordinator_conformance())
    print("ALL REDIS COORDINATOR INTEGRATION TESTS PASSED SUCCESSFULLY!")
