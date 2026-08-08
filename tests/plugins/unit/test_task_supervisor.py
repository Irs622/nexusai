"""
Unit tests for TaskSupervisor async task tracking and cancellation.
"""

import asyncio

import pytest

from nexusai.plugins.runtime.supervisor import TaskSupervisor


@pytest.mark.asyncio
async def test_task_supervisor_tracking_and_cancel():
    supervisor = TaskSupervisor()

    async def long_running_task() -> None:
        await asyncio.sleep(10)

    task = asyncio.create_task(long_running_task())
    supervisor.track_task("plugin.worker", task)

    assert len(supervisor.get_tasks("plugin.worker")) == 1

    await supervisor.cancel_plugin_tasks("plugin.worker")
    assert len(supervisor.get_tasks("plugin.worker")) == 0
    assert task.cancelled() is True
