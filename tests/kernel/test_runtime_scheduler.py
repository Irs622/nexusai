"""
Unit tests for RuntimeScheduler.
"""

import asyncio

import pytest

from nexusai.kernel.scheduler import RuntimeScheduler


@pytest.mark.asyncio
async def test_runtime_scheduler_periodic_and_once_execution():
    scheduler = RuntimeScheduler()
    scheduler.start()

    execution_counts = {"periodic": 0, "once": 0}

    async def _periodic_fn():
        execution_counts["periodic"] += 1

    async def _once_fn():
        execution_counts["once"] += 1

    scheduler.schedule_periodic("test_periodic", interval_seconds=0.05, task_fn=_periodic_fn)
    scheduler.schedule_once("test_once", delay_seconds=0.02, task_fn=_once_fn)

    await asyncio.sleep(0.12)

    tasks = scheduler.list_tasks()
    assert len(tasks) == 2
    assert execution_counts["periodic"] >= 2
    assert execution_counts["once"] == 1

    await scheduler.stop()
    assert scheduler.is_running is False


@pytest.mark.asyncio
async def test_runtime_scheduler_exception_isolation():
    scheduler = RuntimeScheduler()
    scheduler.start()

    async def _failing_task():
        raise ValueError("Simulated task error")

    scheduler.schedule_once("fail_task", delay_seconds=0.01, task_fn=_failing_task)
    await asyncio.sleep(0.05)

    tasks = scheduler.list_tasks()
    fail_meta = next(t for t in tasks if t["name"] == "fail_task")
    assert fail_meta["failures_count"] == 1
    assert "Simulated task error" in fail_meta["last_error"]

    await scheduler.stop()
