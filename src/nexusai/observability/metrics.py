"""
Token latency tracking and TelemetryCollector metrics engine.
"""

from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass
class TokenLatencyMetric:
    """Metric record for streaming LLM response token latencies."""

    provider: str
    model: str
    time_to_first_token_ms: float
    total_duration_ms: float
    token_count: int

    @property
    def tokens_per_second(self) -> float:
        """Calculate tokens generated per second."""
        if self.total_duration_ms <= 0:
            return 0.0
        return (self.token_count / self.total_duration_ms) * 1000.0


class TokenLatencyTracker:
    """Tracks TTFT and throughput metrics for streaming provider requests."""

    def __init__(self, provider: str, model: str) -> None:
        self.provider = provider
        self.model = model
        self.start_time: float = time.time()
        self.first_token_time: float | None = None
        self.token_count: int = 0

    def record_first_token(self) -> None:
        """Mark timestamp of first generated token."""
        if self.first_token_time is None:
            self.first_token_time = time.time()

    def record_token(self) -> None:
        """Increment generated token counter."""
        self.token_count += 1

    def finalize(self) -> TokenLatencyMetric:
        """Compute final token latency metric record."""
        end_time = time.time()
        ttft = (self.first_token_time - self.start_time) * 1000.0 if self.first_token_time else 0.0
        total_duration = (end_time - self.start_time) * 1000.0

        return TokenLatencyMetric(
            provider=self.provider,
            model=self.model,
            time_to_first_token_ms=ttft,
            total_duration_ms=total_duration,
            token_count=self.token_count,
        )


class TelemetryCollector:
    """Centralized metrics collection engine for kernel and providers."""

    def __init__(self) -> None:
        self._latency_records: list[TokenLatencyMetric] = []

    def record_token_latency(self, metric: TokenLatencyMetric) -> None:
        """Record token latency metric."""
        self._latency_records.append(metric)

    def get_token_latency_records(self) -> list[TokenLatencyMetric]:
        """Return recorded token latency metrics."""
        return list(self._latency_records)

    def clear(self) -> None:
        """Clear recorded telemetry metrics."""
        self._latency_records.clear()
