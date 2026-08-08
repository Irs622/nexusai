"""
Automation & Proactive Scheduler Package.
"""

from typing import Any

__all__ = ["SchedulerService"]


def __getattr__(name: str) -> Any:
    if name == "SchedulerService":
        from nexusai.automation.scheduler import SchedulerService

        return SchedulerService
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
