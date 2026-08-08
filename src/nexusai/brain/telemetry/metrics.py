"""Runtime Telemetry abstractions for NexusAI Agent Runtime.

Provides lightweight, zero-dependency, injectable metrics collection for context compaction,
turn latency, context units reclaimed, and failure pattern telemetry.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class CompactionMetricsSnapshot:
    """Immutable snapshot of accumulated runtime context compaction metrics.

    Attributes:
        trigger_count: Total number of compaction runs triggered.
        skipped_count: Total number of compaction runs bypassed (warning threshold safe).
        failures_count: Total number of recorded execution failures.
        summary_count: Total number of SummaryBlock objects generated.
        total_duration_ms: Total cumulative compaction execution time in milliseconds.
        average_duration_ms: Mean compaction duration per run in milliseconds.
        p95_duration_ms: 95th percentile compaction duration in milliseconds.
        last_compaction_duration_ms: Duration in ms of most recent compaction run.
        last_units_saved: Units reclaimed in most recent compaction run.
        last_failure_reason: Error message of most recent failure event.
        last_trigger_timestamp: Epoch timestamp of most recent trigger run.
        total_units_before: Accumulated ContextUnits prior to compaction runs.
        total_units_after: Accumulated ContextUnits after compaction runs.
        total_units_saved: Accumulated ContextUnits reclaimed by compaction.
        total_observations_before: Total active observations prior to compaction.
        total_observations_after: Total active observations after compaction.
        failures_by_category: Map of failure category counts.
    """

    trigger_count: int = 0
    skipped_count: int = 0
    failures_count: int = 0
    summary_count: int = 0
    total_duration_ms: float = 0.0
    average_duration_ms: float = 0.0
    p95_duration_ms: float = 0.0
    last_compaction_duration_ms: float = 0.0
    last_units_saved: int = 0
    last_failure_reason: str = ""
    last_trigger_timestamp: float = 0.0
    total_units_before: int = 0
    total_units_after: int = 0
    total_units_saved: int = 0
    total_observations_before: int = 0
    total_observations_after: int = 0
    failures_by_category: dict[str, int] = field(default_factory=dict)


@runtime_checkable
class IMetricsCollector(Protocol):
    """Protocol interface for lightweight runtime telemetry collection."""

    def record_compaction(
        self,
        duration_ms: float,
        units_before: int,
        units_after: int,
        obs_before: int,
        obs_after: int,
        was_triggered: bool,
        summary_created: bool,
        session_id: str | None = None,
    ) -> None:
        """Record telemetry for a single context compaction execution."""
        ...

    def record_failure(
        self,
        category: str,
        tool_name: str,
        reason: str = "",
        session_id: str | None = None,
    ) -> None:
        """Record an execution failure event."""
        ...

    def snapshot(self) -> CompactionMetricsSnapshot:
        """Return an immutable snapshot of accumulated telemetry metrics."""
        ...

    def reset(self) -> None:
        """Reset accumulated metrics counter state."""
        ...


class InMemoryMetricsCollector:
    """Default thread-safe in-memory telemetry metrics accumulator.

    Zero third-party vendor SDK dependencies.
    """

    def __init__(self) -> None:
        self._durations_ms: list[float] = []
        self._trigger_count: int = 0
        self._skipped_count: int = 0
        self._failures_count: int = 0
        self._summary_count: int = 0
        self._units_before: int = 0
        self._units_after: int = 0
        self._obs_before: int = 0
        self._obs_after: int = 0
        self._last_duration_ms: float = 0.0
        self._last_units_saved: int = 0
        self._last_failure_reason: str = ""
        self._last_trigger_timestamp: float = 0.0
        self._failures_by_category: dict[str, int] = {}
        self._session_durations: dict[str, list[float]] = {}

    def record_compaction(
        self,
        duration_ms: float,
        units_before: int,
        units_after: int,
        obs_before: int,
        obs_after: int,
        was_triggered: bool,
        summary_created: bool,
        session_id: str | None = None,
    ) -> None:
        """Record telemetry for a single context compaction execution."""
        if len(self._durations_ms) < 5000:
            self._durations_ms.append(duration_ms)
        self._last_duration_ms = duration_ms

        if session_id:
            if session_id not in self._session_durations:
                self._session_durations[session_id] = []
            self._session_durations[session_id].append(duration_ms)

        if was_triggered:
            self._trigger_count += 1
            self._units_before += units_before
            self._units_after += units_after
            self._obs_before += obs_before
            self._obs_after += obs_after
            self._last_units_saved = max(0, units_before - units_after)
            self._last_trigger_timestamp = time.time()
        else:
            self._skipped_count += 1

        if summary_created:
            self._summary_count += 1

    def record_failure(
        self,
        category: str,
        tool_name: str,
        reason: str = "",
        session_id: str | None = None,
    ) -> None:
        """Record an execution failure event."""
        self._failures_count += 1
        cat_key = category or "UNKNOWN"
        self._failures_by_category[cat_key] = self._failures_by_category.get(cat_key, 0) + 1
        self._last_failure_reason = reason or f"Tool '{tool_name}' failure ({cat_key})"

    def snapshot(self) -> CompactionMetricsSnapshot:
        """Return an immutable snapshot of accumulated telemetry metrics."""
        total_runs = len(self._durations_ms)
        if total_runs == 0:
            return CompactionMetricsSnapshot()

        tot_dur = sum(self._durations_ms)
        avg_dur = tot_dur / total_runs

        sorted_dur = sorted(self._durations_ms)
        p95_idx = int(0.95 * total_runs)
        if p95_idx >= total_runs:
            p95_idx = total_runs - 1
        p95_dur = sorted_dur[p95_idx]

        units_saved = max(0, self._units_before - self._units_after)

        return CompactionMetricsSnapshot(
            trigger_count=self._trigger_count,
            skipped_count=self._skipped_count,
            failures_count=self._failures_count,
            summary_count=self._summary_count,
            total_duration_ms=round(tot_dur, 2),
            average_duration_ms=round(avg_dur, 2),
            p95_duration_ms=round(p95_dur, 2),
            last_compaction_duration_ms=round(self._last_duration_ms, 2),
            last_units_saved=self._last_units_saved,
            last_failure_reason=self._last_failure_reason,
            last_trigger_timestamp=self._last_trigger_timestamp,
            total_units_before=self._units_before,
            total_units_after=self._units_after,
            total_units_saved=units_saved,
            total_observations_before=self._obs_before,
            total_observations_after=self._obs_after,
            failures_by_category=dict(self._failures_by_category),
        )

    def reset(self) -> None:
        """Reset accumulated metrics counter state."""
        self._durations_ms.clear()
        self._trigger_count = 0
        self._skipped_count = 0
        self._failures_count = 0
        self._summary_count = 0
        self._units_before = 0
        self._units_after = 0
        self._obs_before = 0
        self._obs_after = 0
        self._last_duration_ms = 0.0
        self._last_units_saved = 0
        self._last_failure_reason = ""
        self._last_trigger_timestamp = 0.0
        self._failures_by_category.clear()
        self._session_durations.clear()
