"""Unit test suite for SQLiteExecutionJournal write-ahead lifecycle logging."""

from __future__ import annotations

import asyncio
import os
import tempfile
import pytest

from nexusai.brain.domain.execution_recovery import JournalEntry, JournalLifecyclePhase
from nexusai.infrastructure.persistence.sqlite_execution_journal import SQLiteExecutionJournal


@pytest.mark.asyncio
async def test_sqlite_execution_journal_crud_and_active_executions() -> None:
    """Test SQLiteExecutionJournal appends entries, retrieves latest, and filters non-terminal active executions."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name

    try:
        journal = SQLiteExecutionJournal(db_path=db_path)

        entry1 = JournalEntry(
            entry_id="j1",
            session_id="sess-1",
            execution_id="exec-1",
            plan_fingerprint="fp-1",
            node_id="n1",
            tool_id="tool1",
            action_digest="ad1",
            phase=JournalLifecyclePhase.PLANNING,
        )
        await journal.append_entry(entry1)

        entry2 = JournalEntry(
            entry_id="j2",
            session_id="sess-1",
            execution_id="exec-1",
            plan_fingerprint="fp-1",
            node_id="n1",
            tool_id="tool1",
            action_digest="ad1",
            phase=JournalLifecyclePhase.READY_TO_EXECUTE,
        )
        await journal.append_entry(entry2)

        # Retrieve latest entry
        latest = await journal.get_latest_entry("exec-1")
        assert latest is not None
        assert latest.phase == JournalLifecyclePhase.READY_TO_EXECUTE

        # Check active executions list
        active = await journal.get_active_executions()
        assert "exec-1" in active

        # Transition to COMPLETED -> Should no longer appear in active executions
        entry3 = JournalEntry(
            entry_id="j3",
            session_id="sess-1",
            execution_id="exec-1",
            plan_fingerprint="fp-1",
            node_id="n1",
            tool_id="tool1",
            action_digest="ad1",
            phase=JournalLifecyclePhase.COMPLETED,
        )
        await journal.append_entry(entry3)

        active_after = await journal.get_active_executions()
        assert "exec-1" not in active_after

    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


if __name__ == "__main__":
    asyncio.run(test_sqlite_execution_journal_crud_and_active_executions())
    print("ALL EXECUTION JOURNAL UNIT TESTS PASSED SUCCESSFULLY!")
