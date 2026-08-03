"""Retry Policy with Error Classification and Exponential Backoff Middleware."""

from __future__ import annotations

import asyncio
import random
from typing import Sequence, Type

from nexusai.core.annotations import stable
from nexusai.logging.logger import logger
from nexusai.providers.clock import Clock, SystemClock
from nexusai.providers.exceptions import (
    ProviderAuthenticationError,
    ProviderCircuitOpenError,
    ProviderConfigurationError,
    ProviderNetworkError,
    ProviderRateLimitError,
    ProviderRegistrationError,
    ProviderSDKError,
    ProviderTimeoutError,
)
from nexusai.providers.middleware import BaseMiddleware, NextHandler
from nexusai.providers.models import ChatRequest, ChatResponse
from nexusai.providers.session import ProviderSession


@stable
class RetryDecider:
    """Decider evaluating whether an exception is retryable based on Error Taxonomy."""

    NON_RETRYABLE_EXCEPTIONS: tuple[Type[Exception], ...] = (
        ProviderAuthenticationError,
        ProviderRegistrationError,
        ProviderConfigurationError,
        ProviderCircuitOpenError,
    )

    RETRYABLE_EXCEPTIONS: tuple[Type[Exception], ...] = (
        ProviderTimeoutError,
        ProviderNetworkError,
        ProviderRateLimitError,
    )

    def is_retryable(self, exception: Exception) -> bool:
        """Determine if an exception should be retried.

        Args:
            exception: The caught exception instance.

        Returns:
            True if retryable, False otherwise.
        """
        if isinstance(exception, self.NON_RETRYABLE_EXCEPTIONS):
            return False
        return isinstance(exception, self.RETRYABLE_EXCEPTIONS)


@stable
class RetryPolicy:
    """Retry policy calculation helper with exponential backoff and full jitter."""

    def __init__(
        self,
        max_retries: int = 3,
        initial_delay_seconds: float = 1.0,
        max_delay_seconds: float = 30.0,
        backoff_factor: float = 2.0,
        decider: RetryDecider | None = None,
    ) -> None:
        self.max_retries = max_retries
        self.initial_delay_seconds = initial_delay_seconds
        self.max_delay_seconds = max_delay_seconds
        self.backoff_factor = backoff_factor
        self.decider = decider or RetryDecider()

    def calculate_delay(self, attempt: int) -> float:
        """Calculate exponential backoff delay with jitter."""
        calculated = self.initial_delay_seconds * (self.backoff_factor ** (attempt - 1))
        capped = min(calculated, self.max_delay_seconds)
        return random.uniform(0, capped)

    def should_retry(self, attempt: int, exception: Exception) -> bool:
        """Check if request should be retried for attempt count and exception."""
        if attempt > self.max_retries:
            return False
        return self.decider.is_retryable(exception)


@stable
class RetryMiddleware(BaseMiddleware):
    """Middleware executing automated request retries based on RetryPolicy."""

    def __init__(self, policy: RetryPolicy | None = None, clock: Clock | None = None) -> None:
        self.policy = policy or RetryPolicy()
        self.clock = clock or SystemClock()

    async def process(
        self,
        request: ChatRequest,
        next_call: NextHandler,
        session: ProviderSession | None = None,
    ) -> ChatResponse:

        attempt = 1
        while True:
            try:
                return await next_call(request)
            except Exception as err:
                if not self.policy.should_retry(attempt, err):
                    raise
                delay = self.policy.calculate_delay(attempt)
                logger.warning(
                    "RetryMiddleware: Attempt {}/{} failed ({}), retrying in {:.2f}s...",
                    attempt,
                    self.policy.max_retries,
                    err,
                    delay,
                )
                await self.clock.sleep(delay)
                attempt += 1
