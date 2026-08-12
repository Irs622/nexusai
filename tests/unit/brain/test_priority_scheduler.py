"""Unit tests for PriorityScheduler, task priority dispatch, aging starvation protection, and atomic claim."""

from __future__ import annotations

import asyncio
import time
import pytest

from nexusai.brain.domain.scheduler import (
    ScheduledTask,
    SchedulerClosedError,
    TaskPriority,
    compute_effective_priority,
)
from nexusai.brain.runtime.priority_scheduler import PriorityScheduler


@pytest.mark.asyncio
async def test_atomic_claim_concurrent_consumers() -> None:
    """Test Atomic Claim: Multiple concurrent consumers acquire distinct tasks without race conditions."""
    scheduler = PriorityScheduler()

    task1 = ScheduledTask(task_id="t1", execution_id="e1", node_id=1, priority=TaskPriority.NORMAL)
    task2 = ScheduledTask(task_id="t2", execution_id="e1", node_id=2, priority=TaskPriority.NORMAL)
    await scheduler.submit(task1)
    await scheduler.submit(task2)

    c1 = asyncio.create_task(scheduler.next())
    c2 = asyncio.create_task(scheduler.next())

    claimed1, claimed2 = await asyncio.gather(c1, c2)

    assert claimed1.task_id != claimed2.task_id
    assert {claimed1.task_id, claimed2.task_id} == {"t1", "t2"}
    assert await scheduler.size() == 0


@pytest.mark.asyncio
async def test_deterministic_priority_and_tie_breaking() -> None:
    """Test Deterministic Tie Breaking: Order is effective_priority DESC, queued_at ASC, task_id ASC."""
    scheduler = PriorityScheduler(aging_rate=0.0)  # Disable aging for pure priority test

    # Submit out of order
    await scheduler.submit(ScheduledTask(task_id="t_low", execution_id="e1", node_id=1, priority=TaskPriority.LOW))
    await scheduler.submit(ScheduledTask(task_id="t_high_b", execution_id="e1", node_id=2, priority=TaskPriority.HIGH))
    await scheduler.submit(ScheduledTask(task_id="t_high_a", execution_id="e1", node_id=3, priority=TaskPriority.HIGH))

    # Highest priority items (t_high_a and t_high_b) should tie break on task_id ASC -> t_high_a first
    res1 = await scheduler.next()
    res2 = await scheduler.next()
    res3 = await scheduler.next()

    assert res1.task_id == "t_high_a"
    assert res2.task_id == "t_high_b"
    assert res3.task_id == "t_low"


@pytest.mark.asyncio
async def test_aging_boost_prevents_starvation() -> None:
    """Test Aging Engine: Aged LOW task eventually exceeds fresh HIGH task in effective priority."""
    scheduler = PriorityScheduler(aging_rate=10.0)  # High aging rate for test

    now = time.time()
    # LOW task queued 5 seconds ago -> effective_priority = 0 + (5 * 10) = 50
    old_low = ScheduledTask(
        task_id="t_old_low", execution_id="e1", node_id=1, priority=TaskPriority.LOW, queued_at=now - 5.0
    )
    # Fresh HIGH task queued now -> effective_priority = 20 + (0 * 10) = 20
    fresh_high = ScheduledTask(
        task_id="t_fresh_high", execution_id="e1", node_id=2, priority=TaskPriority.HIGH, queued_at=now
    )

    await scheduler.submit(old_low)
    await scheduler.submit(fresh_high)

    res1 = await scheduler.next()
    assert res1.task_id == "t_old_low", "Aged LOW task must exceed fresh HIGH task in effective priority"


@pytest.mark.asyncio
async def test_retry_aging_isolation() -> None:
    """Test Retry Aging Isolation: Retried task resets queued_at timestamp upon queue admission."""
    scheduler = PriorityScheduler()

    now = time.time()
    task = ScheduledTask(
        task_id="t_retry",
        execution_id="e1",
        node_id=1,
        created_at=now - 100.0,  # Created 100s ago
        queued_at=now - 100.0,
    )
    await scheduler.submit(task)

    claimed = await scheduler.next()
    # Admitted task queued_at was updated to current time (within 1s)
    assert claimed.queued_at > now - 1.0


@pytest.mark.asyncio
async def test_delayed_retry_queue_wakeup() -> None:
    """Test Delayed Queue: Task with delay_until is held until timestamp elapses, then dispatched."""
    scheduler = PriorityScheduler()

    now = time.time()
    delayed_task = ScheduledTask(
        task_id="t_delay",
        execution_id="e1",
        node_id=1,
        delay_until=now + 0.1,  # Delayed 100ms
    )
    await scheduler.submit(delayed_task)

    assert await scheduler.get_delayed_count() == 1

    t0 = time.perf_counter()
    claimed = await scheduler.next()
    elapsed = time.perf_counter() - t0

    assert claimed.task_id == "t_delay"
    assert elapsed >= 0.08, f"Task was claimed too early ({elapsed:.3f}s)"
    assert await scheduler.get_delayed_count() == 0


@pytest.mark.asyncio
async def test_scheduler_shutdown_behavior() -> None:
    """Test Shutdown: Shutdown wakes blocked next() consumers with SchedulerClosedError and rejects submit()."""
    scheduler = PriorityScheduler()

    consumer_task = asyncio.create_task(scheduler.next())
    await asyncio.sleep(0.02)

    await scheduler.shutdown()

    with pytest.raises(SchedulerClosedError, match="Scheduler is shutdown"):
        await consumer_task

    with pytest.raises(SchedulerClosedError, match="Cannot submit task to a shutdown scheduler"):
        await scheduler.submit(ScheduledTask(task_id="t1", execution_id="e1", node_id=1))


@pytest.mark.asyncio
async def test_task_cancellation() -> None:
    """Test Cancellation: cancel(task_id) removes ready and delayed tasks from scheduler."""
    scheduler = PriorityScheduler()

    now = time.time()
    await scheduler.submit(ScheduledTask(task_id="t_ready", execution_id="e1", node_id=1))
    await scheduler.submit(ScheduledTask(task_id="t_delay", execution_id="e1", node_id=2, delay_until=now + 10.0))

    assert await scheduler.size() == 2

    assert await scheduler.cancel("t_ready") is True
    assert await scheduler.cancel("t_delay") is True
    assert await scheduler.cancel("non_existent") is False

    assert await scheduler.size() == 0


if __name__ == "__main__":
    asyncio.run(test_atomic_claim_concurrent_consumers())
    asyncio.run(test_deterministic_priority_and_tie_breaking())
    asyncio.run(test_aging_boost_prevents_starvation())
    asyncio.run(test_retry_aging_isolation())
    asyncio.run(test_delayed_retry_queue_wakeup())
    asyncio.run(test_scheduler_shutdown_behavior())
    asyncio.run(test_task_cancellation())
    print("ALL P2-3 PRIORITY SCHEDULER UNIT TESTS PASSED SUCCESSFULLY!")
