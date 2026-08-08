"""
Runtime Scheduler for time-based periodic and one-shot background kernel tasks.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from nexusai.logging.logger import logger


@dataclass
class ScheduledTaskMeta:
    """Metadata tracking scheduled task execution."""

    name: str
    is_periodic: bool
    interval_seconds: float
    delay_seconds: float
    runs_count: int = 0
    failures_count: int = 0
    last_run: str | None = None
    last_error: str | None = None
    is_active: bool = True


class RuntimeScheduler:
    """Asyncio-native time-based task scheduler for OS Kernel periodic routines."""

    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task[Any]] = {}
        self._meta: dict[str, ScheduledTaskMeta] = {}
        self._is_running: bool = False

    @property
    def is_running(self) -> bool:
        """Return True if the scheduler is active."""
        return self._is_running

    def start(self) -> None:
        """Start the scheduler."""
        self._is_running = True
        logger.info("RuntimeScheduler started.")

    async def stop(self) -> None:
        """Stop scheduler and cancel all pending/active scheduled tasks."""
        self._is_running = False
        logger.info("Stopping RuntimeScheduler and cancelling active tasks...")

        for name, task in list(self._tasks.items()):
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            if name in self._meta:
                self._meta[name].is_active = False

        self._tasks.clear()
        logger.info("RuntimeScheduler stopped.")

    def schedule_periodic(
        self,
        name: str,
        interval_seconds: float,
        task_fn: Callable[[], Awaitable[None]],
    ) -> None:
        """Schedule a periodic task running every interval_seconds."""
        if name in self._tasks and not self._tasks[name].done():
            logger.warning(f"Scheduled task '{name}' is already active. Overwriting...")
            self.cancel_task(name)

        meta = ScheduledTaskMeta(
            name=name,
            is_periodic=True,
            interval_seconds=interval_seconds,
            delay_seconds=0.0,
        )
        self._meta[name] = meta

        async def _loop() -> None:
            while self._is_running and meta.is_active:
                await asyncio.sleep(interval_seconds)
                if not self._is_running or not meta.is_active:
                    break
                await self._execute_task(name, task_fn, meta)

        if self._is_running:
            self._tasks[name] = asyncio.create_task(_loop(), name=f"scheduler_{name}")

    def schedule_once(
        self,
        name: str,
        delay_seconds: float,
        task_fn: Callable[[], Awaitable[None]],
    ) -> None:
        """Schedule a one-shot task running after delay_seconds."""
        if name in self._tasks and not self._tasks[name].done():
            self.cancel_task(name)

        meta = ScheduledTaskMeta(
            name=name,
            is_periodic=False,
            interval_seconds=0.0,
            delay_seconds=delay_seconds,
        )
        self._meta[name] = meta

        async def _run_once() -> None:
            await asyncio.sleep(delay_seconds)
            if self._is_running and meta.is_active:
                await self._execute_task(name, task_fn, meta)
            meta.is_active = False

        if self._is_running:
            self._tasks[name] = asyncio.create_task(_run_once(), name=f"scheduler_once_{name}")

    def cancel_task(self, name: str) -> bool:
        """Cancel a scheduled task by name."""
        if name in self._tasks:
            task = self._tasks.pop(name)
            if not task.done():
                task.cancel()
            if name in self._meta:
                self._meta[name].is_active = False
            logger.info(f"Cancelled scheduled task '{name}'.")
            return True
        return False

    def list_tasks(self) -> list[dict[str, Any]]:
        """Return status metrics dictionary of all scheduled tasks."""
        return [
            {
                "name": meta.name,
                "is_periodic": meta.is_periodic,
                "interval_seconds": meta.interval_seconds,
                "delay_seconds": meta.delay_seconds,
                "runs_count": meta.runs_count,
                "failures_count": meta.failures_count,
                "last_run": meta.last_run,
                "last_error": meta.last_error,
                "is_active": meta.is_active
                and (meta.name in self._tasks and not self._tasks[meta.name].done()),
            }
            for meta in self._meta.values()
        ]

    async def _execute_task(
        self,
        name: str,
        task_fn: Callable[[], Awaitable[None]],
        meta: ScheduledTaskMeta,
    ) -> None:
        """Execute task_fn with exception isolation."""
        try:
            meta.runs_count += 1
            meta.last_run = datetime.now(timezone.utc).isoformat()
            await task_fn()
        except asyncio.CancelledError:
            raise
        except Exception as err:
            meta.failures_count += 1
            meta.last_error = str(err)
            logger.error(f"Error executing scheduled task '{name}': {err}")
