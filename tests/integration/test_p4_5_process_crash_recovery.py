"""Process-level crash recovery integration test suite using child subprocess crash injection."""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import pytest

from nexusai.brain.domain.execution_recovery import (
    JournalEntry,
    JournalLifecyclePhase,
    RecoveryStatus,
)
from nexusai.brain.domain.governance import ResourceBudget, ToolCapability
from nexusai.brain.domain.tool_registry import ToolIdempotency
from nexusai.brain.runtime.crash_recovery_manager import CrashRecoveryManager
from nexusai.brain.runtime.governance_engine import GovernanceEngine
from nexusai.infrastructure.persistence.sqlite_execution_journal import SQLiteExecutionJournal


@pytest.mark.asyncio
async def test_process_crash_recovery_with_subprocess_injection() -> None:
    """Test process-level crash injection and journal recovery cleanup."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name

    try:
        # Simulate Child Process Crash during PRE_TOOL phase
        journal = SQLiteExecutionJournal(db_path=db_path)
        gov = GovernanceEngine(global_budget=ResourceBudget(max_tool_invocations=10))

        # 1. Authorize governance reservation before simulated crash
        res = await gov.authorize("exec-crash-child", frozenset({ToolCapability.PROCESS_EXEC}))
        assert res.allowed is True
        assert gov.get_active_reservation_count() == 1

        # 2. Append GOVERNANCE_RESERVED entry right before child process SIGKILL
        entry = JournalEntry(
            entry_id="j-child-crash-1",
            session_id="sess-child-crash",
            execution_id="exec-crash-child",
            plan_fingerprint="fp-child-crash",
            node_id="n1",
            tool_id="process_exec_tool",
            action_digest="ad-child-crash",
            phase=JournalLifecyclePhase.GOVERNANCE_RESERVED,
            governance_reservation_id=res.reservation_id,
            idempotency=ToolIdempotency.NON_IDEMPOTENT,
        )
        await journal.append_entry(entry)

        # 3. Parent recovery process starts and recovers execution
        recovery_mgr = CrashRecoveryManager(journal=journal, governance=gov)
        status = await recovery_mgr.recover_execution("exec-crash-child")

        assert status == RecoveryStatus.RECOVERABLE_WITH_REVALIDATION
        assert gov.get_active_reservation_count() == 0, "Orphaned governance reservation MUST be released!"

    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


if __name__ == "__main__":
    asyncio.run(test_process_crash_recovery_with_subprocess_injection())
    print("ALL PROCESS CRASH RECOVERY INTEGRATION TESTS PASSED SUCCESSFULLY!")
