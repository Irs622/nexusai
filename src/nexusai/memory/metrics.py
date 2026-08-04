"""
MemoryMetricsCollector for latency tracking, counters, and percentile calculations.
"""

from __future__ import annotations

import time
from typing import Any


class MemoryMetricsCollector:
    """Telemetry collector measuring storage, vector, and embedding performance metrics."""

    def __init__(self) -> None:
        self._latencies: dict[str, list[float]] = {
            "storage_save": [],
            "storage_get": [],
            "vector_search": [],
            "embedding": [],
            "pipeline_total": [],
        }
        self._counters: dict[str, int] = {
            "store_count": 0,
            "search_count": 0,
            "forget_count": 0,
            "failure_count": 0,
        }

    def record_latency(self, metric_name: str, latency_ms: float) -> None:
        """Record latency measurement in milliseconds."""
        if metric_name not in self._latencies:
            self._latencies[metric_name] = []
        self._latencies[metric_name].append(latency_ms)

    def increment_counter(self, counter_name: str, amount: int = 1) -> None:
        """Increment telemetry counter."""
        if counter_name not in self._counters:
            self._counters[counter_name] = 0
        self._counters[counter_name] += amount

    def get_percentiles(self, metric_name: str) -> dict[str, float]:
        """Calculate P50, P95, P99 percentile latencies for target metric."""
        samples = sorted(self._latencies.get(metric_name, []))
        if not samples:
            return {"p50": 0.0, "p95": 0.0, "p99": 0.0, "count": 0}

        n = len(samples)
        p50 = samples[int(n * 0.50)]
        p95 = samples[min(n - 1, int(n * 0.95))]
        p99 = samples[min(n - 1, int(n * 0.99))]

        return {
            "p50": p50,
            "p95": p95,
            "p99": p99,
            "count": n,
        }

    def get_summary(self) -> dict[str, Any]:
        """Return comprehensive metrics summary dictionary."""
        percentiles_summary = {
            metric: self.get_percentiles(metric) for metric in self._latencies
        }
        return {
            "counters": dict(self._counters),
            "percentiles": percentiles_summary,
        }
