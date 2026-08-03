"""Per-Provider Circuit Breaker Pattern implementation for Model Providers."""
import time
from enum import Enum
from typing import Optional, Dict, Any
from nexusai.core.errors import ModelProviderError

class CircuitState(str, Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"

class CircuitBreaker:
    """Configurable state machine managing per-provider failure thresholds and metrics."""

    def __init__(
        self,
        provider_id: str = "default_provider",
        failure_threshold: int = 5,
        recovery_timeout_seconds: float = 30.0,
    ) -> None:
        self.provider_id = provider_id
        self.failure_threshold = failure_threshold
        self.recovery_timeout_seconds = recovery_timeout_seconds
        
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.total_failures = 0
        self.trip_count = 0
        self.last_failure_time: float = 0.0

    def can_execute(self) -> bool:
        """Check if request is allowed through the circuit breaker."""
        now = time.time()
        if self.state == CircuitState.OPEN:
            if now - self.last_failure_time > self.recovery_timeout_seconds:
                self.state = CircuitState.HALF_OPEN
                return True
            return False
        return True

    def record_success(self) -> None:
        """Record successful call and reset state to CLOSED."""
        self.failure_count = 0
        self.state = CircuitState.CLOSED

    def record_failure(self) -> None:
        """Record failure and trip to OPEN state if threshold reached."""
        self.failure_count += 1
        self.total_failures += 1
        self.last_failure_time = time.time()
        if self.failure_count >= self.failure_threshold:
            if self.state != CircuitState.OPEN:
                self.trip_count += 1
            self.state = CircuitState.OPEN

    def get_metrics(self) -> Dict[str, Any]:
        """Export circuit breaker metrics and health state."""
        return {
            "provider_id": self.provider_id,
            "state": self.state.value,
            "failure_count": self.failure_count,
            "total_failures": self.total_failures,
            "trip_count": self.trip_count,
            "last_failure_time": self.last_failure_time,
        }
