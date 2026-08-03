"""
Unit tests for SchedulerService, NotifyTool, and ScheduleReminderTool.
"""

import pytest
from unittest.mock import AsyncMock, patch

from nexusai.automation.scheduler import SchedulerService
from nexusai.core.errors import CommandExecutionError
from nexusai.security.guard import RiskLevel
from nexusai.tools.automation.schedule_tool import ScheduleReminderTool
from nexusai.tools.macos.notify import NotifyTool, send_macos_notification
from nexusai.tools.registry import ToolRegistry


def dummy_job_function() -> str:
    return "Job Executed"


@pytest.mark.asyncio
async def test_scheduler_service_lifecycle() -> None:
    scheduler = SchedulerService()
    assert not scheduler.is_running

    scheduler.start()
    assert scheduler.is_running

    scheduler.stop()
    assert not scheduler.is_running


@pytest.mark.asyncio
async def test_scheduler_service_add_delayed_and_cron_tasks() -> None:
    scheduler = SchedulerService()
    scheduler.start()

    try:
        job_id = scheduler.add_delayed_task(10, dummy_job_function)
        assert job_id is not None

        cron_job_id = scheduler.add_cron_task("*/5 * * * *", dummy_job_function)
        assert cron_job_id is not None

        with pytest.raises(CommandExecutionError):
            scheduler.add_cron_task("invalid_cron_syntax", dummy_job_function)
    finally:
        scheduler.stop()


@pytest.mark.asyncio
async def test_send_macos_notification_escaping() -> None:
    mock_process = AsyncMock()
    mock_process.communicate.return_value = (b"", b"")

    with patch("asyncio.create_subprocess_exec", return_value=mock_process) as mock_exec:
        await send_macos_notification(
            title='Reminder "Important"',
            message='Push "code" to git',
        )

        mock_exec.assert_called_once()
        args = mock_exec.call_args[0]
        assert args[0] == "osascript"
        assert args[1] == "-e"
        assert 'Reminder \\"Important\\"' in args[2]
        assert 'Push \\"code\\" to git' in args[2]


@pytest.mark.asyncio
async def test_notify_tool() -> None:
    tool = NotifyTool()
    assert tool.name == "macos_send_notification"
    assert tool.risk_level == RiskLevel.LOW

    with patch("nexusai.tools.macos.notify.send_macos_notification", return_value=None) as mock_notify:
        result = await tool.execute(title="Build", message="Success")
        mock_notify.assert_called_once_with("Build", "Success")
        assert "Desktop notification sent" in result


@pytest.mark.asyncio
async def test_schedule_reminder_tool() -> None:
    scheduler = SchedulerService()
    scheduler.start()

    try:
        tool = ScheduleReminderTool(scheduler=scheduler)
        assert tool.name == "automation_schedule_reminder"
        assert tool.risk_level == RiskLevel.LOW

        result = await tool.execute(delay_minutes=15, message="Push commits to GitHub")
        assert "Reminder scheduled to trigger in 15 minute(s)" in result
        assert "Job ID:" in result
    finally:
        scheduler.stop()


def test_automation_tools_registry() -> None:
    registry = ToolRegistry()
    registry.register(NotifyTool())
    registry.register(ScheduleReminderTool())

    assert registry.has_tool("macos_send_notification")
    assert registry.has_tool("automation_schedule_reminder")
