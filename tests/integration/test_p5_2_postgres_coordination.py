"""PostgresExecutionCoordinator contract conformance integration test suite."""

from __future__ import annotations

import asyncio
import pytest

from nexusai.infrastructure.coordination.postgres_execution_coordinator import PostgresExecutionCoordinator
from tests.contracts.test_execution_coordinator_contract import verify_coordinator_contract


@pytest.mark.asyncio
async def test_postgres_coordinator_conformance() -> None:
    """Verify PostgresExecutionCoordinator satisfies full IExecutionCoordinator domain contract."""
    coord = PostgresExecutionCoordinator()
    await verify_coordinator_contract(coord)


if __name__ == "__main__":
    asyncio.run(test_postgres_coordinator_conformance())
    print("ALL POSTGRES COORDINATOR INTEGRATION TESTS PASSED SUCCESSFULLY!")
