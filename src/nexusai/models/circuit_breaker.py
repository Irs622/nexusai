"""Per-Provider Circuit Breaker Pattern with Sliding Window Metrics & Health Score."""
import time
from enum import Enum
from typing import Optional, Dict, Any, List

class CircuitState(str, Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"

class CircuitBreaker:
    """Configurable state machine managing per-provider failure thresholds, sliding window metrics, and health scores."""

    def __init__(
        self,
        provider_id: str = "default_provider",
        failure_threshold: int = 5,
        recovery_timeout_seconds: float = 30.0,
        sliding_window_size: int = 50,
    ) -> None:
        self.provider_id = provider_id
        self.failure_threshold = failure_threshold
        self.recovery_timeout_seconds = recovery_timeout_seconds
        self.sliding_window_size = sliding_window_size
        
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.total_failures = 0
        self.trip_count = 0
        self.last_failure_time: float = 0.0
        
        self._history: List[tuple[bool, float]] = []

    def can_execute(self) -> bool:
        """Check if request is allowed through the circuit breaker."""
        now = time.time()
        if self.state == CircuitState.OPEN:
            if now - self.last_failure_time > self.recovery_timeout_seconds:
                self.state = CircuitState.HALF_OPEN
                return True
            return False
        return True

    def record_success(self, latency_ms: float = 0.0) -> None:
        """Record successful call and update sliding window metrics."""
        self.failure_count = 0
        self.state = CircuitState.CLOSED
        self._record_history(True, latency_ms)

    def record_failure(self, latency_ms: float = 0.0) -> None:
        """Record failure and trip to OPEN state if threshold reached."""
        self.failure_count += 1
        self.total_failures += 1
        self.last_failure_time = time.time()
        self._record_history(False, latency_ms)
        
        if self.failure_count >= self.failure_threshold:
            if self.state != CircuitState.OPEN:
                self.trip_count += 1
            self.state = CircuitState.OPEN

    def _record_history(self, success: bool, latency_ms: float) -> None:
        self._history.append((success, latency_ms))
        if len(self._history) > self.sliding_window_size:
            self._history.pop(0)

    def calculate_health_score(self) -> float:
        """Calculate dynamic health score between 0.0 and 1.0 (0.5 * success_ratio + 0.3 * latency_score + 0.2 * availability)."""
        total = len(self._history)
        if total == 0:
            return 1.0 if self.state == CircuitState.CLOSED else 0.0

        successes = sum(1 for s, _ in self._history if s)
        success_ratio = successes / total

        latencies = [lat for _, lat in self._history if lat > 0]
        avg_latency = (sum(latencies) / len(latencies)) if latencies else 0.0
        latency_score = max(0.0, 1.0 - (avg_latency / 2000.0))

        availability = 0.0 if self.state == CircuitState.OPEN else (0.5 if self.state == CircuitState.HALF_OPEN else 1.0)
        
        score = (0.5 * success_ratio) + (0.3 * latency_score) + (0.2 * availability)
        return round(score, 2)

    def get_metrics(self) -> Dict[str, Any]:
        """Export circuit breaker metrics, sliding window health state, and health score."""
        total = len(self._history)
        successes = sum(1 for s, _ in self._history if s)
        success_ratio = (successes / total) if total > 0 else 1.0
        latencies = [lat for _, lat in self._history if lat > 0]
        avg_latency = (sum(latencies) / len(latencies)) if latencies else 0.0

        return {
            "provider_id": self.provider_id,
            "state": self.state.value,
            "failure_count": self.failure_count,
            "total_failures": self.total_failures,
            "trip_count": self.trip_count,
            "last_failure_time": self.last_failure_time,
            "sliding_window_sample_size": total,
            "success_ratio": round(success_ratio, 2),
            "avg_latency_ms": round(avg_latency, 2),
            "health_score": self.calculate_health_score(),
        }
