"""Circuit Breaker pattern for protecting provider endpoints from cascading failures.

This is the single canonical implementation (ADR 0037). ``nexusai.runtime.circuit_breaker``
and ``nexusai.models.circuit_breaker`` are deprecated aliases of this module.
"""

from __future__ import annotations

from collections import deque
from enum import Enum
from typing import Any, Awaitable, Callable

from nexusai.core.annotations import stable
from nexusai.logging.logger import logger
from nexusai.providers.clock import Clock, SystemClock
from nexusai.providers.exceptions import ProviderCircuitOpenError


@stable
class CircuitState(str, Enum):
    """States of a CircuitBreaker."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@stable
class CircuitBreaker:
    """Circuit Breaker guarding provider calls against repeated cascading failures.

    Besides the CLOSED/OPEN/HALF_OPEN state machine, it keeps a sliding window of recent
    call outcomes and latencies, used for health scoring and metrics export.
    """

    def __init__(
        self,
        provider_id: str,
        failure_threshold: int = 5,
        recovery_timeout_seconds: float = 30.0,
        success_threshold: int = 2,
        clock: Clock | None = None,
        sliding_window_size: int = 50,
    ) -> None:
        self.provider_id = provider_id
        self.failure_threshold = failure_threshold
        self.recovery_timeout_seconds = recovery_timeout_seconds
        self.success_threshold = success_threshold
        self.clock = clock or SystemClock()
        self.sliding_window_size = sliding_window_size

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_state_change = self.clock.time()

        self.total_failures = 0
        self.trip_count = 0
        self.last_failure_time: float = 0.0
        self._history: deque[tuple[bool, float]] = deque(maxlen=sliding_window_size)

    @property
    def state(self) -> CircuitState:
        """Current state of circuit breaker."""
        if self._state == CircuitState.OPEN:
            if self.clock.time() - self._last_state_change > self.recovery_timeout_seconds:
                self._transition_to(CircuitState.HALF_OPEN)
        return self._state

    @property
    def failure_count(self) -> int:
        """Consecutive failures recorded since the last reset."""
        return self._failure_count

    def can_execute(self) -> bool:
        """Return whether a request is currently allowed through (non-raising check)."""
        return self.state != CircuitState.OPEN

    def _transition_to(self, new_state: CircuitState) -> None:
        logger.info(
            "CircuitBreaker '{}' transition: {} -> {}",
            self.provider_id,
            self._state.value,
            new_state.value,
        )
        if new_state == CircuitState.OPEN and self._state != CircuitState.OPEN:
            self.trip_count += 1
        self._state = new_state
        self._last_state_change = self.clock.time()
        if new_state == CircuitState.CLOSED:
            self._failure_count = 0
            self._success_count = 0
        elif new_state == CircuitState.HALF_OPEN:
            self._success_count = 0

    def record_success(self, latency_ms: float = 0.0) -> None:
        """Record successful provider request."""
        self._history.append((True, latency_ms))
        if self.state == CircuitState.HALF_OPEN:
            self._success_count += 1
            if self._success_count >= self.success_threshold:
                self._transition_to(CircuitState.CLOSED)
        elif self.state == CircuitState.CLOSED:
            self._failure_count = 0

    def record_failure(self, error: Exception | None = None, latency_ms: float = 0.0) -> None:
        """Record failed provider request."""
        self._failure_count += 1
        self.total_failures += 1
        self.last_failure_time = self.clock.time()
        self._history.append((False, latency_ms))
        logger.warning(
            "CircuitBreaker '{}' recorded failure ({}/{}): {}",
            self.provider_id,
            self._failure_count,
            self.failure_threshold,
            error,
        )
        if self._failure_count >= self.failure_threshold or self.state == CircuitState.HALF_OPEN:
            self._transition_to(CircuitState.OPEN)

    def _window_stats(self) -> tuple[int, float, float]:
        total = len(self._history)
        successes = sum(1 for ok, _ in self._history if ok)
        success_ratio = (successes / total) if total > 0 else 1.0
        latencies = [lat for _, lat in self._history if lat > 0]
        avg_latency = (sum(latencies) / len(latencies)) if latencies else 0.0
        return total, success_ratio, avg_latency

    def calculate_health_score(self) -> float:
        """Health score in [0.0, 1.0]: 0.5 * success_ratio + 0.3 * latency_score + 0.2 * availability."""
        state = self.state
        total, success_ratio, avg_latency = self._window_stats()
        if total == 0:
            return 1.0 if state == CircuitState.CLOSED else 0.0

        latency_score = max(0.0, 1.0 - (avg_latency / 2000.0))
        availability = {CircuitState.CLOSED: 1.0, CircuitState.HALF_OPEN: 0.5}.get(state, 0.0)
        score = (0.5 * success_ratio) + (0.3 * latency_score) + (0.2 * availability)
        return round(score, 2)

    def get_metrics(self) -> dict[str, Any]:
        """Export circuit breaker state, sliding window statistics, and health score."""
        total, success_ratio, avg_latency = self._window_stats()
        return {
            "provider_id": self.provider_id,
            "state": self.state.value,
            "failure_count": self._failure_count,
            "total_failures": self.total_failures,
            "trip_count": self.trip_count,
            "last_failure_time": self.last_failure_time,
            "sliding_window_sample_size": total,
            "success_ratio": round(success_ratio, 2),
            "avg_latency_ms": round(avg_latency, 2),
            "health_score": self.calculate_health_score(),
        }

    async def call(self, fn: Callable[..., Awaitable[Any]], *args: Any, **kwargs: Any) -> Any:
        """Execute a coroutine function guarded by CircuitBreaker.

        Raises:
            ProviderCircuitOpenError: If state is OPEN.
        """
        if self.state == CircuitState.OPEN:
            raise ProviderCircuitOpenError(
                f"Circuit breaker for provider '{self.provider_id}' is OPEN. Requests blocked."
            )

        start = self.clock.time()
        try:
            result = await fn(*args, **kwargs)
        except Exception as err:
            self.record_failure(err, latency_ms=(self.clock.time() - start) * 1000.0)
            raise
        self.record_success(latency_ms=(self.clock.time() - start) * 1000.0)
        return result
