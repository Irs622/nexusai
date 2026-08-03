"""Circuit Breaker pattern for protecting provider endpoints from cascading failures."""

from __future__ import annotations

import asyncio
from enum import Enum
import time
from typing import Any, Awaitable, Callable

from nexusai.core.annotations import stable
from nexusai.logging.logger import logger
from nexusai.providers.exceptions import ProviderCircuitOpenError


@stable
class CircuitState(str, Enum):
    """States of a CircuitBreaker."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@stable
class CircuitBreaker:
    """Circuit Breaker guarding provider calls against repeated cascading failures."""

    def __init__(

        self,
        provider_id: str,
        failure_threshold: int = 5,
        recovery_timeout_seconds: float = 30.0,
        success_threshold: int = 2,
    ) -> None:
        self.provider_id = provider_id
        self.failure_threshold = failure_threshold
        self.recovery_timeout_seconds = recovery_timeout_seconds
        self.success_threshold = success_threshold

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_state_change = time.time()

    @property
    def state(self) -> CircuitState:
        """Current state of circuit breaker."""
        if self._state == CircuitState.OPEN:
            if time.time() - self._last_state_change > self.recovery_timeout_seconds:
                self._transition_to(CircuitState.HALF_OPEN)
        return self._state

    def _transition_to(self, new_state: CircuitState) -> None:
        logger.info("CircuitBreaker '{}' transition: {} -> {}", self.provider_id, self._state.value, new_state.value)
        self._state = new_state
        self._last_state_change = time.time()
        if new_state == CircuitState.CLOSED:
            self._failure_count = 0
            self._success_count = 0
        elif new_state == CircuitState.HALF_OPEN:
            self._success_count = 0

    def record_success(self) -> None:
        """Record successful provider request."""
        if self.state == CircuitState.HALF_OPEN:
            self._success_count += 1
            if self._success_count >= self.success_threshold:
                self._transition_to(CircuitState.CLOSED)
        elif self.state == CircuitState.CLOSED:
            self._failure_count = 0

    def record_failure(self, error: Exception) -> None:
        """Record failed provider request."""
        self._failure_count += 1
        logger.warning(
            "CircuitBreaker '{}' recorded failure ({}/{}): {}",
            self.provider_id,
            self._failure_count,
            self.failure_threshold,
            error,
        )
        if self._failure_count >= self.failure_threshold or self.state == CircuitState.HALF_OPEN:
            self._transition_to(CircuitState.OPEN)

    async def call(self, fn: Callable[..., Awaitable[Any]], *args: Any, **kwargs: Any) -> Any:
        """Execute a coroutine function guarded by CircuitBreaker.

        Raises:
            ProviderCircuitOpenError: If state is OPEN.
        """
        if self.state == CircuitState.OPEN:
            raise ProviderCircuitOpenError(
                f"Circuit breaker for provider '{self.provider_id}' is OPEN. Requests blocked."
            )

        try:
            result = await fn(*args, **kwargs)
            self.record_success()
            return result
        except Exception as err:
            self.record_failure(err)
            raise
