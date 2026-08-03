"""Dynamic runtime metrics and EWMA latency tracking for provider adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from nexusai.core.annotations import stable


@stable
@dataclass
class ProviderRuntimeMetrics:
    """Dynamic runtime performance metrics for tracking provider health and latency."""

    request_count: int = 0
    success_count: int = 0
    error_count: int = 0
    last_error: str | None = None
    last_checked_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # Latency tracking
    ewma_latency_ms: float = 0.0
    alpha: float = 0.2  # EWMA smoothing factor
    rolling_latencies: list[float] = field(default_factory=list)
    max_rolling_window: int = 50

    def record_success(self, latency_ms: float) -> None:
        """Record a successful request execution and update EWMA & rolling window latency.

        Args:
            latency_ms: Execution duration in milliseconds.
        """
        self.request_count += 1
        self.success_count += 1
        self.last_checked_at = datetime.now(timezone.utc)

        # Update EWMA
        if self.ewma_latency_ms == 0.0:
            self.ewma_latency_ms = latency_ms
        else:
            self.ewma_latency_ms = (self.alpha * latency_ms) + ((1 - self.alpha) * self.ewma_latency_ms)

        # Update rolling window
        self.rolling_latencies.append(latency_ms)
        if len(self.rolling_latencies) > self.max_rolling_window:
            self.rolling_latencies.pop(0)

    def record_error(self, error: str) -> None:
        """Record a request failure.

        Args:
            error: Error message or traceback summary.
        """
        self.request_count += 1
        self.error_count += 1
        self.last_error = error
        self.last_checked_at = datetime.now(timezone.utc)

    @property
    def success_rate(self) -> float:
        """Calculate recent request success rate (0.0 to 1.0)."""
        if self.request_count == 0:
            return 1.0
        return self.success_count / self.request_count
