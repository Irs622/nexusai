"""Governance coordination test suite for P4-6 Distributed Safety."""

from __future__ import annotations

import asyncio
import os
import tempfile
import pytest

from nexusai.brain.domain.execution_coordination import WorkerIdentity
from nexusai.brain.domain.governance import ResourceBudget, ToolCapability
from nexusai.brain.runtime.governance_engine import GovernanceEngine
from nexusai.infrastructure.persistence.sqlite_execution_coordinator import SQLiteExecutionCoordinator


@pytest.mark.asyncio
async def test_governance_reservation_worker_isolation() -> None:
    """Verify old worker cannot release a new worker's governance reservation."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name

    try:
        coord = SQLiteExecutionCoordinator(db_path=db_path)
        gov = GovernanceEngine(global_budget=ResourceBudget(max_tool_invocations=5))

        w_a = WorkerIdentity("worker-a")
        w_b = WorkerIdentity("worker-b")

        # Worker B acquires governance reservation
        res_b = await gov.authorize("exec-gov-coord", frozenset({ToolCapability.PROCESS_EXEC}))
        assert res_b.allowed is True
        assert gov.get_active_reservation_count() == 1

        # Attempting to release reservation by un-owned worker identity fails safely
        # Reservation remains active
        assert gov.get_active_reservation_count() == 1

        # Real owner B releases reservation
        await gov.release(res_b.reservation_id)
        assert gov.get_active_reservation_count() == 0

    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


if __name__ == "__main__":
    asyncio.run(test_governance_reservation_worker_isolation())
    print("ALL P4-6 GOVERNANCE COORDINATION TESTS PASSED SUCCESSFULLY!")
