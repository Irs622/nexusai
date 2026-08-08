"""ExecutionPolicy and CircuitBreaker for runtime tool execution sandboxing and policy enforcement."""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum


class CircuitBreakerState(str, Enum):
    """Circuit breaker state classification."""

    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitBreakerOpenError(RuntimeError):
    """Exception raised when a tool call is tripped by CircuitBreaker."""

    pass


class CircuitBreaker:
    """Circuit breaker tracking tool execution failure rates and preventing cascading failures."""

    def __init__(self, failure_threshold: int = 3, reset_timeout_sec: float = 10.0) -> None:
        self.failure_threshold = failure_threshold
        self.reset_timeout_sec = reset_timeout_sec
        self._state = CircuitBreakerState.CLOSED
        self._failure_count = 0
        self._last_failure_time = 0.0

    @property
    def state(self) -> CircuitBreakerState:
        if self._state == CircuitBreakerState.OPEN:
            if time.time() - self._last_failure_time > self.reset_timeout_sec:
                self._state = CircuitBreakerState.HALF_OPEN
        return self._state

    def record_success(self) -> None:
        """Record successful execution and reset state."""
        self._failure_count = 0
        self._state = CircuitBreakerState.CLOSED

    def record_failure(self) -> None:
        """Record failed execution and trip circuit if threshold reached."""
        self._failure_count += 1
        self._last_failure_time = time.time()
        if self._failure_count >= self.failure_threshold:
            self._state = CircuitBreakerState.OPEN

    def check_execution_allowed(self) -> None:
        """Check if execution is permitted, raising CircuitBreakerOpenError if tripped."""
        if self.state == CircuitBreakerState.OPEN:
            raise CircuitBreakerOpenError(
                "CircuitBreaker is OPEN — tool execution tripped due to high failure rate"
            )


@dataclass(frozen=True)
class ExecutionPolicy:
    """Execution policy enforcing sandboxing timeouts, retry budgets, and circuit breakers.

    Attributes:
        timeout_sec: Maximum tool execution timeout limit in seconds.
        retry_budget: Maximum allowed retry attempts.
        backoff_factor: Exponential backoff factor.
        enable_circuit_breaker: Boolean flag toggling circuit breaker protection.
    """

    timeout_sec: float = 30.0
    retry_budget: int = 3
    backoff_factor: float = 2.0
    enable_circuit_breaker: bool = True
