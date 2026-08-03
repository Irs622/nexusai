from __future__ import annotations

"""
Schedule Reminder Tool for Proactive Automation.
"""

from typing import Any
from pydantic import BaseModel, Field

from nexusai.automation.scheduler import SchedulerService
from nexusai.security.guard import RiskLevel
from nexusai.tools.base import BaseTool
from nexusai.tools.macos.notify import send_macos_notification


class ScheduleReminderInputSchema(BaseModel):
    """Input schema for automation_schedule_reminder tool."""

    delay_minutes: int = Field(..., description="Time delay in minutes before firing the reminder notification")
    message: str = Field(..., description="The reminder message text to display")


class ScheduleReminderTool(BaseTool):
    """Tool scheduling future macOS desktop reminders using the SchedulerService."""

    name = "automation_schedule_reminder"
    description = "Schedules a native macOS notification to remind the user about something in the future."
    risk_level = RiskLevel.LOW
    input_schema = ScheduleReminderInputSchema

    def __init__(self, scheduler: SchedulerService | None = None) -> None:
        self.scheduler = scheduler or SchedulerService()

    async def execute(self, delay_minutes: int, message: str, **kwargs: Any) -> str:
        """Schedule future reminder task."""
        delay_seconds = max(1, delay_minutes * 60)
        job_id = self.scheduler.add_delayed_task(
            delay_seconds,
            send_macos_notification,
            "NexusAI Reminder",
            message,
        )
        return f"Reminder scheduled to trigger in {delay_minutes} minute(s) (Job ID: {job_id})."
