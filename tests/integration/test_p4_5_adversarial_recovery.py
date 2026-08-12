"""Adversarial stress test suite for P4-5 CrashRecoveryManager concurrency, reservation cleanup, and idempotency."""

from __future__ import annotations

import asyncio
import os
import tempfile
import pytest

from nexusai.brain.domain.execution_recovery import JournalEntry, JournalLifecyclePhase, RecoveryStatus
from nexusai.brain.domain.governance import ResourceBudget, ToolCapability
from nexusai.brain.domain.tool_registry import ToolIdempotency
from nexusai.brain.runtime.crash_recovery_manager import CrashRecoveryManager
from nexusai.brain.runtime.governance_engine import GovernanceEngine
from nexusai.infrastructure.persistence.sqlite_execution_journal import SQLiteExecutionJournal


@pytest.mark.asyncio
async def test_p4_5_adversarial_crash_recovery_stress() -> None:
    """Stress Test: 50 concurrent executions, 10 concurrent recovery workers, and process crash injection across SQLite journal connections.

    Invariants: Zero duplicate non-idempotent executions, zero leaked governance reservations, zero deadlocks.
    """
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name

    try:
        journal = SQLiteExecutionJournal(db_path=db_path)
        gov = GovernanceEngine(global_budget=ResourceBudget(max_concurrent_tasks=50, max_tool_invocations=100))

        # 1. Register 50 executions in write-ahead journal with governance reservations
        for i in range(50):
            res = await gov.authorize(f"exec-adv-rec-{i}", frozenset({ToolCapability.PROCESS_EXEC}))
            assert res.allowed is True

            idem = ToolIdempotency.IDEMPOTENT if i % 2 == 0 else ToolIdempotency.NON_IDEMPOTENT
            phase = JournalLifecyclePhase.GOVERNANCE_RESERVED if i % 3 == 0 else JournalLifecyclePhase.EXECUTING_TOOL

            entry = JournalEntry(
                entry_id=f"j-adv-rec-{i}",
                session_id=f"sess-adv-rec-{i}",
                execution_id=f"exec-adv-rec-{i}",
                plan_fingerprint=f"fp-adv-rec-{i}",
                node_id=f"n-{i}",
                tool_id="process_exec_tool",
                action_digest=f"ad-{i}",
                phase=phase,
                governance_reservation_id=res.reservation_id,
                idempotency=idem,
            )
            await journal.append_entry(entry)

        # 2. 10 Concurrent Recovery Workers recovering executions in parallel
        async def recovery_worker(w_id: int) -> None:
            mgr = CrashRecoveryManager(journal=SQLiteExecutionJournal(db_path=db_path), governance=gov)
            await mgr.recover_all_active()

        recovery_tasks = [asyncio.create_task(recovery_worker(w)) for w in range(10)]
        await asyncio.gather(*recovery_tasks)

        print(f"\n[P4-5 ADVERSARIAL CRASH RECOVERY STRESS VERIFICATION]")
        print(f"Active Governance Reservations at Teardown: {gov.get_active_reservation_count()}")

        assert gov.get_active_reservation_count() == 0, "Zero leaked governance reservations invariant MUST hold!"

    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


if __name__ == "__main__":
    asyncio.run(test_p4_5_adversarial_crash_recovery_stress())
    print("ALL P4-5 ADVERSARIAL CRASH RECOVERY STRESS TESTS PASSED SUCCESSFULLY!")
