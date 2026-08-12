"""Governance reservation cleanup integration test suite for P4-5 Crash Recovery."""

from __future__ import annotations

import asyncio
import os
import tempfile
import pytest

from nexusai.brain.domain.execution_recovery import JournalEntry, JournalLifecyclePhase
from nexusai.brain.domain.governance import ResourceBudget, ToolCapability
from nexusai.brain.runtime.crash_recovery_manager import CrashRecoveryManager
from nexusai.brain.runtime.governance_engine import GovernanceEngine
from nexusai.infrastructure.persistence.sqlite_execution_journal import SQLiteExecutionJournal


@pytest.mark.asyncio
async def test_governance_reservation_orphaned_cleanup() -> None:
    """Verify CrashRecoveryManager releases orphaned governance reservations upon recovery."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name

    try:
        journal = SQLiteExecutionJournal(db_path=db_path)
        gov = GovernanceEngine(global_budget=ResourceBudget(max_tool_invocations=5))
        mgr = CrashRecoveryManager(journal=journal, governance=gov)

        res = await gov.authorize("exec-gov-leak", frozenset({ToolCapability.PROCESS_EXEC}))
        assert res.allowed is True
        assert gov.get_active_reservation_count() == 1

        entry = JournalEntry(
            entry_id="j-gov-1",
            session_id="s1",
            execution_id="exec-gov-leak",
            plan_fingerprint="fp1",
            node_id="n1",
            tool_id="process_exec_tool",
            action_digest="ad1",
            phase=JournalLifecyclePhase.GOVERNANCE_RESERVED,
            governance_reservation_id=res.reservation_id,
        )
        await journal.append_entry(entry)

        # Recover -> Governance reservation released cleanly
        await mgr.recover_execution("exec-gov-leak")
        assert gov.get_active_reservation_count() == 0

    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


if __name__ == "__main__":
    asyncio.run(test_governance_reservation_orphaned_cleanup())
    print("ALL P4-5 GOVERNANCE RECOVERY TESTS PASSED SUCCESSFULLY!")
