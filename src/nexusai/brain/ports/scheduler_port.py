"""IScheduler port contract for task dispatch, queue governance, and starvation protection."""

from __future__ import annotations

from typing import Protocol

from nexusai.brain.domain.scheduler import ScheduledTask


class IScheduler(Protocol):
    """Abstract port interface decoupling task scheduling governance from the execution engine."""

    async def submit(self, task: ScheduledTask) -> None:
        """Submit a new or retried task to the scheduler."""
        ...

    async def next(self) -> ScheduledTask:
        """Wait for eligible task and atomically claim ownership of the highest priority task."""
        ...

    async def cancel(self, task_id: str) -> bool:
        """Cancel a pending or delayed task in the scheduler queues."""
        ...

    async def size(self) -> int:
        """Return total number of pending and delayed tasks owned by the scheduler."""
        ...

    async def get_ready_count(self) -> int:
        """Return count of tasks currently ready and unclaimed."""
        ...

    async def get_delayed_count(self) -> int:
        """Return count of tasks awaiting RETRY_WAIT delay timestamps."""
        ...

    async def shutdown(self) -> None:
        """Gracefully shut down scheduler, waking blocked consumers and rejecting future submissions."""
        ...

    @property
    def is_shutdown(self) -> bool:
        """Return whether scheduler has been shut down."""
        ...
