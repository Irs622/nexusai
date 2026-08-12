"""Tool idempotency recovery test suite for P4-5 Crash Recovery."""

from __future__ import annotations

import asyncio
import os
import tempfile
import pytest

from nexusai.brain.domain.execution_recovery import JournalEntry, JournalLifecyclePhase, RecoveryStatus
from nexusai.brain.domain.tool_registry import ToolIdempotency
from nexusai.brain.runtime.crash_recovery_manager import CrashRecoveryManager
from nexusai.infrastructure.persistence.sqlite_execution_journal import SQLiteExecutionJournal


@pytest.mark.asyncio
async def test_tool_idempotency_recovery_classification() -> None:
    """Verify CrashRecoveryManager differentiates IDEMPOTENT vs NON_IDEMPOTENT tool crash recovery."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name

    try:
        journal = SQLiteExecutionJournal(db_path=db_path)
        mgr = CrashRecoveryManager(journal=journal)

        # 1. Idempotent tool crash -> RECOVERABLE_WITH_REVALIDATION
        entry_idem = JournalEntry(
            entry_id="j-idem-1",
            session_id="s1",
            execution_id="exec-idem-1",
            plan_fingerprint="fp1",
            node_id="n1",
            tool_id="file_read_tool",
            action_digest="ad1",
            phase=JournalLifecyclePhase.EXECUTING_TOOL,
            idempotency=ToolIdempotency.IDEMPOTENT,
        )
        await journal.append_entry(entry_idem)
        st_idem = await mgr.recover_execution("exec-idem-1")
        assert st_idem == RecoveryStatus.RECOVERABLE_WITH_REVALIDATION

        # 2. Non-idempotent tool crash -> AMBIGUOUS_SIDE_EFFECT
        entry_non_idem = JournalEntry(
            entry_id="j-non-idem-1",
            session_id="s1",
            execution_id="exec-non-idem-1",
            plan_fingerprint="fp1",
            node_id="n1",
            tool_id="process_exec_tool",
            action_digest="ad1",
            phase=JournalLifecyclePhase.EXECUTING_TOOL,
            idempotency=ToolIdempotency.NON_IDEMPOTENT,
        )
        await journal.append_entry(entry_non_idem)
        st_non_idem = await mgr.recover_execution("exec-non-idem-1")
        assert st_non_idem == RecoveryStatus.AMBIGUOUS_SIDE_EFFECT

    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


if __name__ == "__main__":
    asyncio.run(test_tool_idempotency_recovery_classification())
    print("ALL P4-5 TOOL IDEMPOTENCY RECOVERY TESTS PASSED SUCCESSFULLY!")
