"""
Background AsyncIOScheduler Service for Proactive Automation.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger

from nexusai.core.errors import CommandExecutionError


class SchedulerService:
    """Service managing non-blocking background jobs and scheduled reminders."""

    def __init__(self, scheduler: AsyncIOScheduler | None = None) -> None:
        self.scheduler = scheduler or AsyncIOScheduler()
        self._running = False

    def start(self) -> None:
        """Start the background scheduler lifecycle."""
        if not self._running:
            if not self.scheduler.running:
                self.scheduler.start()
            self._running = True

    def stop(self) -> None:
        """Shutdown the background scheduler cleanly."""
        if self._running:
            if self.scheduler.running:
                try:
                    self.scheduler.shutdown(wait=False)
                except Exception:
                    pass
            self._running = False

    @property
    def is_running(self) -> bool:
        """Check if scheduler is running."""
        return self._running

    def add_delayed_task(
        self,
        delay_seconds: int,
        func: Callable[..., Any],
        *args: Any,
    ) -> str:
        """Schedule a one-off task after a delay in seconds.

        Args:
            delay_seconds: Seconds to wait before execution.
            func: Callable task to execute.
            *args: Positional arguments to pass to func.

        Returns:
            Unique scheduled job ID.
        """
        run_date = datetime.now(timezone.utc) + timedelta(seconds=delay_seconds)
        trigger = DateTrigger(run_date=run_date)
        job = self.scheduler.add_job(func, trigger=trigger, args=args)
        return str(job.id)

    def add_cron_task(
        self,
        cron_expression: str,
        func: Callable[..., Any],
        *args: Any,
    ) -> str:
        """Schedule a recurring cron job.

        Args:
            cron_expression: Standard 5-field cron string (e.g. '*/5 * * * *').
            func: Callable task to execute.
            *args: Positional arguments to pass to func.

        Returns:
            Unique scheduled job ID.
        """
        try:
            trigger = CronTrigger.from_crontab(cron_expression)
            job = self.scheduler.add_job(func, trigger=trigger, args=args)
            return str(job.id)
        except Exception as e:
            raise CommandExecutionError(f"Invalid cron expression '{cron_expression}': {e}") from e
