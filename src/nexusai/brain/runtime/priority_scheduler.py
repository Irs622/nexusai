"""PriorityScheduler runtime implementation with atomic claim, starvation protection, delayed retry dispatch, and telemetry instrumentation."""

from __future__ import annotations

import asyncio
from dataclasses import replace
import time
from typing import Any

from nexusai.brain.domain.observability import RuntimeEvent, RuntimeEventType
from nexusai.brain.domain.scheduler import (
    ScheduledTask,
    SchedulerClosedError,
    compute_effective_priority,
)
from nexusai.brain.ports.observability_port import IObservabilityPort
from nexusai.brain.ports.scheduler_port import IScheduler


class PriorityScheduler(IScheduler):
    """Thread and coroutine safe Priority Scheduler with atomic claim, aging boost, condition-driven wakeup, and telemetry."""

    def __init__(
        self,
        aging_rate: float = 0.5,
        telemetry: IObservabilityPort | None = None,
    ) -> None:
        self.aging_rate = aging_rate
        self.telemetry = telemetry
        self._cond = asyncio.Condition()
        self._ready_tasks: list[ScheduledTask] = []
        self._delayed_tasks: list[ScheduledTask] = []
        self._claimed_task_ids: set[str] = set()
        self._is_shutdown: bool = False

    @property
    def is_shutdown(self) -> bool:
        """Return whether scheduler has been shut down."""
        return self._is_shutdown

    async def _emit_gauges(self) -> None:
        """Emit queue depth metrics with fault isolation."""
        if not self.telemetry:
            return
        try:
            now = time.time()
            total_size = len(self._ready_tasks) + len(self._delayed_tasks)
            ready_cnt = sum(1 for t in self._ready_tasks if t.task_id not in self._claimed_task_ids)
            delayed_cnt = sum(1 for t in self._delayed_tasks if t.delay_until is not None and t.delay_until > now)

            await self.telemetry.record_gauge("nexusai_scheduler_queue_depth", float(total_size))
            await self.telemetry.record_gauge("nexusai_scheduler_ready_depth", float(ready_cnt))
            await self.telemetry.record_gauge("nexusai_scheduler_delayed_depth", float(delayed_cnt))
        except Exception:
            pass

    async def submit(self, task: ScheduledTask) -> None:
        """Submit a new or retried task to the scheduler."""
        async with self._cond:
            if self._is_shutdown:
                if self.telemetry:
                    try:
                        await self.telemetry.increment_counter("nexusai_scheduler_rejected_total")
                    except Exception:
                        pass
                raise SchedulerClosedError("Cannot submit task to a shutdown scheduler")

            now = time.time()
            admitted_task = replace(task, queued_at=now)

            if admitted_task.delay_until is not None and admitted_task.delay_until > now:
                self._delayed_tasks.append(admitted_task)
            else:
                self._ready_tasks.append(admitted_task)

            self._cond.notify_all()

        if self.telemetry:
            try:
                await self.telemetry.emit_event(
                    RuntimeEvent(
                        event_id=f"sched-sub-{admitted_task.task_id}-{int(now * 1000)}",
                        event_type=RuntimeEventType.SCHEDULER_SUBMITTED,
                        execution_id=admitted_task.execution_id,
                        node_id=str(admitted_task.node_id),
                        task_id=admitted_task.task_id,
                        attributes={"priority": admitted_task.priority.name},
                    )
                )
                await self.telemetry.increment_counter("nexusai_scheduler_submitted_total")
                await self._emit_gauges()
            except Exception:
                pass

    async def next(self) -> ScheduledTask:
        """Wait for eligible task and atomically claim ownership of the highest priority task."""
        async with self._cond:
            while True:
                if self._is_shutdown:
                    raise SchedulerClosedError("Scheduler is shutdown")

                now = time.time()

                still_delayed = []
                for dt in self._delayed_tasks:
                    if dt.delay_until is None or dt.delay_until <= now:
                        promoted_task = replace(dt, queued_at=now)
                        self._ready_tasks.append(promoted_task)
                    else:
                        still_delayed.append(dt)
                self._delayed_tasks = still_delayed

                if self._ready_tasks:
                    self._ready_tasks.sort(
                        key=lambda t: (
                            -compute_effective_priority(t, now, self.aging_rate),
                            t.queued_at,
                            t.task_id,
                        )
                    )

                    claimed_task = self._ready_tasks.pop(0)
                    self._claimed_task_ids.add(claimed_task.task_id)

                    if self.telemetry:
                        try:
                            wait_ms = (now - claimed_task.queued_at) * 1000.0
                            await self.telemetry.emit_event(
                                RuntimeEvent(
                                    event_id=f"sched-claim-{claimed_task.task_id}-{int(now * 1000)}",
                                    event_type=RuntimeEventType.SCHEDULER_CLAIMED,
                                    execution_id=claimed_task.execution_id,
                                    node_id=str(claimed_task.node_id),
                                    task_id=claimed_task.task_id,
                                    attributes={"wait_ms": wait_ms, "priority": claimed_task.priority.name},
                                )
                            )
                            await self.telemetry.increment_counter("nexusai_scheduler_claimed_total")
                            await self.telemetry.record_duration("nexusai_scheduler_task_wait_ms", max(0.0, wait_ms))
                            await self._emit_gauges()
                        except Exception:
                            pass

                    return claimed_task

                if self._delayed_tasks:
                    earliest_delay = min(t.delay_until for t in self._delayed_tasks if t.delay_until is not None)
                    wait_sec = max(0.001, earliest_delay - now)
                    try:
                        await asyncio.wait_for(self._cond.wait(), timeout=wait_sec)
                    except asyncio.TimeoutError:
                        pass
                else:
                    await self._cond.wait()

    async def cancel(self, task_id: str) -> bool:
        """Cancel a pending or delayed task in the scheduler queues."""
        async with self._cond:
            cancelled_task: ScheduledTask | None = None
            for i, task in enumerate(self._ready_tasks):
                if task.task_id == task_id:
                    cancelled_task = self._ready_tasks.pop(i)
                    self._cond.notify_all()
                    break

            if not cancelled_task:
                for i, task in enumerate(self._delayed_tasks):
                    if task.task_id == task_id:
                        cancelled_task = self._delayed_tasks.pop(i)
                        self._cond.notify_all()
                        break

            if cancelled_task and self.telemetry:
                try:
                    await self.telemetry.emit_event(
                        RuntimeEvent(
                            event_id=f"sched-canc-{task_id}",
                            event_type=RuntimeEventType.SCHEDULER_CANCELLED,
                            execution_id=cancelled_task.execution_id,
                            node_id=str(cancelled_task.node_id),
                            task_id=task_id,
                        )
                    )
                    await self.telemetry.increment_counter("nexusai_scheduler_cancelled_total")
                    await self._emit_gauges()
                except Exception:
                    pass

            return cancelled_task is not None

    async def size(self) -> int:
        """Return total number of pending and delayed tasks owned by the scheduler."""
        async with self._cond:
            return len(self._ready_tasks) + len(self._delayed_tasks)

    async def get_ready_count(self) -> int:
        """Return count of tasks currently ready and unclaimed."""
        async with self._cond:
            return sum(1 for t in self._ready_tasks if t.task_id not in self._claimed_task_ids)

    async def get_delayed_count(self) -> int:
        """Return count of tasks awaiting RETRY_WAIT delay timestamps."""
        async with self._cond:
            now = time.time()
            return sum(1 for t in self._delayed_tasks if t.delay_until is not None and t.delay_until > now)

    async def shutdown(self) -> None:
        """Gracefully shut down scheduler, waking blocked consumers and rejecting future submissions."""
        async with self._cond:
            self._is_shutdown = True
            self._cond.notify_all()

        if self.telemetry:
            try:
                await self.telemetry.emit_event(
                    RuntimeEvent(
                        event_id=f"sched-shutdown-{int(time.time() * 1000)}",
                        event_type=RuntimeEventType.SCHEDULER_SHUTDOWN,
                    )
                )
            except Exception:
                pass
