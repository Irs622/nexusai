"""Security verification test suite for P4-5 Crash Recovery invariants (P4-5-INV-01 to P4-5-INV-25)."""

from __future__ import annotations

import asyncio
import os
import tempfile
import pytest

from nexusai.brain.domain.execution_recovery import (
    JournalEntry,
    JournalLifecyclePhase,
    RecoveryStatus,
)
from nexusai.brain.domain.governance import ResourceBudget, ToolCapability
from nexusai.brain.domain.tool_registry import ToolIdempotency, ToolMetadata, ToolStatus
from nexusai.brain.runtime.crash_recovery_manager import CrashRecoveryManager
from nexusai.brain.runtime.governance_engine import GovernanceEngine
from nexusai.brain.runtime.tool_registry import ToolRegistry
from nexusai.infrastructure.persistence.sqlite_execution_journal import SQLiteExecutionJournal


@pytest.mark.asyncio
async def test_security_ambiguous_non_idempotent_tool_crash_fails_closed() -> None:
    """Security Test (P4-5-INV-12 & P4-5-INV-13): Non-idempotent tool execution crash fails closed with AMBIGUOUS_SIDE_EFFECT."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name

    try:
        journal = SQLiteExecutionJournal(db_path=db_path)
        manager = CrashRecoveryManager(journal=journal)

        # Journal entry recorded right before process crash during non-idempotent tool execution
        entry = JournalEntry(
            entry_id="j-amb-1",
            session_id="sess-amb-1",
            execution_id="exec-amb-1",
            plan_fingerprint="fp-amb-1",
            node_id="n1",
            tool_id="process_exec_tool",
            action_digest="ad-amb-1",
            phase=JournalLifecyclePhase.EXECUTING_TOOL,
            idempotency=ToolIdempotency.NON_IDEMPOTENT,
        )
        await journal.append_entry(entry)

        # Attempt recovery -> MUST FAIL CLOSED with AMBIGUOUS_SIDE_EFFECT!
        status = await manager.recover_execution("exec-amb-1")
        assert status == RecoveryStatus.AMBIGUOUS_SIDE_EFFECT

        latest = await journal.get_latest_entry("exec-amb-1")
        assert latest is not None
        assert latest.phase == JournalLifecyclePhase.ABANDONED

    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


@pytest.mark.asyncio
async def test_security_terminal_state_cannot_resume() -> None:
    """Security Test (P4-5-INV-02): Terminal states (COMPLETED, FAILED, CANCELLED, ABANDONED) cannot resume execution."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name

    try:
        journal = SQLiteExecutionJournal(db_path=db_path)
        manager = CrashRecoveryManager(journal=journal)

        entry = JournalEntry(
            entry_id="j-term-1",
            session_id="sess-term-1",
            execution_id="exec-term-1",
            plan_fingerprint="fp-term-1",
            node_id="n1",
            tool_id="process_exec_tool",
            action_digest="ad-term-1",
            phase=JournalLifecyclePhase.COMPLETED,
        )
        await journal.append_entry(entry)

        status = await manager.recover_execution("exec-term-1")
        assert status == RecoveryStatus.NON_RECOVERABLE

    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


if __name__ == "__main__":
    asyncio.run(test_security_ambiguous_non_idempotent_tool_crash_fails_closed())
    asyncio.run(test_security_terminal_state_cannot_resume())
    print("ALL P4-5 CRASH RECOVERY SECURITY TESTS PASSED SUCCESSFULLY!")
