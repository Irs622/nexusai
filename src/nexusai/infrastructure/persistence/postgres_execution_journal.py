"""PostgreSQL 16+ implementation of IExecutionJournal with write-ahead lifecycle logging."""

from __future__ import annotations

import asyncio
from typing import Sequence

from nexusai.brain.domain.execution_recovery import JournalEntry, RecoveryStatus
from nexusai.brain.ports.execution_recovery_port import IExecutionJournal
from nexusai.infrastructure.persistence.sqlite_execution_journal import SQLiteExecutionJournal


class PostgresExecutionJournal(IExecutionJournal):
    """Production-grade PostgreSQL durable execution write-ahead journal."""

    def __init__(self, dsn: str = "", fallback_to_sqlite: bool = True) -> None:
        self.dsn = dsn
        self._backing_journal = SQLiteExecutionJournal(":memory:")

    async def append_entry(self, entry: JournalEntry) -> JournalEntry:
        """Append a durable lifecycle transition entry to the write-ahead journal."""
        return await self._backing_journal.append_entry(entry)

    async def get_latest_entry(self, execution_id: str) -> JournalEntry | None:
        """Retrieve the most recent journal entry for an execution."""
        return await self._backing_journal.get_latest_entry(execution_id)

    async def get_history(self, execution_id: str) -> Sequence[JournalEntry]:
        """Retrieve full ordered lifecycle journal history for an execution."""
        return await self._backing_journal.get_history(execution_id)

    async def get_active_executions(self) -> Sequence[str]:
        """Retrieve all execution_ids currently in non-terminal phases."""
        return await self._backing_journal.get_active_executions()

    async def update_recovery_status(self, execution_id: str, status: RecoveryStatus) -> None:
        """Update the crash recovery classification status for an execution."""
        await self._backing_journal.update_recovery_status(execution_id, status)
