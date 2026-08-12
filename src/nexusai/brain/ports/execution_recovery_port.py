"""IExecutionJournal protocol contract interface for durable execution lifecycle journaling."""

from __future__ import annotations

from typing import Protocol, Sequence

from nexusai.brain.domain.execution_recovery import JournalEntry, RecoveryStatus


class IExecutionJournal(Protocol):
    """Abstract port interface for durable write-ahead journaling of execution lifecycle transitions."""

    async def append_entry(self, entry: JournalEntry) -> JournalEntry:
        """Append a durable lifecycle transition entry to the write-ahead journal."""
        ...

    async def get_latest_entry(self, execution_id: str) -> JournalEntry | None:
        """Retrieve the most recent journal entry for an execution."""
        ...

    async def get_history(self, execution_id: str) -> Sequence[JournalEntry]:
        """Retrieve full ordered lifecycle journal history for an execution."""
        ...

    async def get_active_executions(self) -> Sequence[str]:
        """Retrieve all execution_ids currently in non-terminal phases."""
        ...

    async def update_recovery_status(self, execution_id: str, status: RecoveryStatus) -> None:
        """Update the crash recovery classification status for an execution."""
        ...
