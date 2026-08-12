"""Unit test suite for CrashRecoveryManager classification and fail-closed safety."""

from __future__ import annotations

import asyncio
import pytest

from nexusai.brain.domain.execution_recovery import (
    JournalEntry,
    JournalLifecyclePhase,
    RecoveryStatus,
)
from nexusai.brain.domain.tool_registry import ToolIdempotency
from nexusai.brain.runtime.crash_recovery_manager import CrashRecoveryManager
from nexusai.infrastructure.persistence.sqlite_execution_journal import SQLiteExecutionJournal


@pytest.mark.asyncio
async def test_crash_recovery_manager_classification_matrix() -> None:
    """Test CrashRecoveryManager classification rules for idempotent vs non-idempotent tools."""
    journal = SQLiteExecutionJournal(":memory:")
    manager = CrashRecoveryManager(journal=journal)

    # 1. WAITING_APPROVAL phase -> RECOVERABLE
    e1 = JournalEntry(
        entry_id="j1",
        session_id="s1",
        execution_id="e1",
        plan_fingerprint="fp1",
        node_id="n1",
        tool_id="process_tool",
        action_digest="ad1",
        phase=JournalLifecyclePhase.WAITING_APPROVAL,
    )
    assert manager.classify_execution_phase(e1) == RecoveryStatus.RECOVERABLE

    # 2. EXECUTING_TOOL for IDEMPOTENT tool -> RECOVERABLE_WITH_REVALIDATION
    e2 = JournalEntry(
        entry_id="j2",
        session_id="s1",
        execution_id="e2",
        plan_fingerprint="fp1",
        node_id="n1",
        tool_id="file_read_tool",
        action_digest="ad1",
        phase=JournalLifecyclePhase.EXECUTING_TOOL,
        idempotency=ToolIdempotency.IDEMPOTENT,
    )
    assert manager.classify_execution_phase(e2) == RecoveryStatus.RECOVERABLE_WITH_REVALIDATION

    # 3. EXECUTING_TOOL for NON_IDEMPOTENT or UNKNOWN tool -> AMBIGUOUS_SIDE_EFFECT (MUST FAIL CLOSED!)
    e3 = JournalEntry(
        entry_id="j3",
        session_id="s1",
        execution_id="e3",
        plan_fingerprint="fp1",
        node_id="n1",
        tool_id="process_exec_tool",
        action_digest="ad1",
        phase=JournalLifecyclePhase.EXECUTING_TOOL,
        idempotency=ToolIdempotency.NON_IDEMPOTENT,
    )
    assert manager.classify_execution_phase(e3) == RecoveryStatus.AMBIGUOUS_SIDE_EFFECT


if __name__ == "__main__":
    asyncio.run(test_crash_recovery_manager_classification_matrix())
    print("ALL CRASH RECOVERY MANAGER UNIT TESTS PASSED SUCCESSFULLY!")
