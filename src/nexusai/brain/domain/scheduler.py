"""Domain models for task scheduling, priority levels, and priority calculation."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import time
from typing import Any, Mapping


class TaskPriority(int, Enum):
    """Task dispatch priority levels (higher integer = higher priority preference)."""

    LOW = 0
    NORMAL = 10
    HIGH = 20
    CRITICAL = 30


class SchedulerClosedError(RuntimeError):
    """Raised when attempting to submit tasks to or consume from a shutdown scheduler."""

    pass


@dataclass(frozen=True)
class ScheduledTask:
    """Immutable domain representation of a task managed by IScheduler."""

    task_id: str
    execution_id: str
    node_id: Any
    priority: TaskPriority = TaskPriority.NORMAL
    delay_until: float | None = None
    created_at: float = field(default_factory=time.time)
    queued_at: float | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


def compute_effective_priority(
    task: ScheduledTask,
    now: float | None = None,
    aging_rate: float = 0.5,
) -> float:
    """Calculate dynamic effective priority with aging boost based on queue wait time.

    Formula: base_priority + (now - queued_at) * aging_rate
    Prevents low-priority task starvation during sustained high-priority submissions.
    """
    current_time = now if now is not None else time.time()
    q_time = task.queued_at if task.queued_at is not None else current_time
    wait_time = max(0.0, current_time - q_time)
    return float(task.priority.value) + (wait_time * aging_rate)

