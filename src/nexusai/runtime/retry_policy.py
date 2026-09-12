"""Configurable Retry Policy with Error Classification and Exponential Backoff for Durable Execution."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any

from nexusai.core.annotations import stable
from nexusai.logging.logger import logger

DEFAULT_RETRYABLE_ERRORS: tuple[str, ...] = (
    "TIMEOUT",
    "TRANSIENT_FAILURE",
    "NETWORK_ERROR",
    "RATE_LIMITED",
    "TRANSIENT",
    "TRANSIENT_ERROR",
    "CONNECTION_RESET",
    "503",
    "504",
)

DEFAULT_NON_RETRYABLE_ERRORS: tuple[str, ...] = (
    "PERMISSION_DENIED",
    "INVALID_INPUT",
    "AUTHENTICATION_ERROR",
    "AUTHORIZATION_ERROR",
    "GOVERNANCE_VIOLATION",
    "INVALID_ARGUMENT",
    "400",
    "401",
    "403",
    "404",
)


@stable
@dataclass
class DurableRetryPolicy:
    """Configurable retry policy with exponential backoff and error classification for durable executions."""

    max_attempts: int = 3
    backoff: str = "exponential"  # "exponential", "linear", "fixed"
    base_delay_seconds: float = 1.0
    max_delay_seconds: float = 60.0
    backoff_factor: float = 2.0
    jitter: bool = True
    retryable_errors: tuple[str, ...] = field(default_factory=lambda: DEFAULT_RETRYABLE_ERRORS)
    non_retryable_errors: tuple[str, ...] = field(
        default_factory=lambda: DEFAULT_NON_RETRYABLE_ERRORS
    )

    def calculate_delay(self, attempt: int) -> float:
        """Calculate retry delay for a given attempt index (1-indexed)."""
        if attempt <= 1:
            raw_delay = self.base_delay_seconds
        elif self.backoff == "exponential":
            raw_delay = self.base_delay_seconds * (self.backoff_factor ** (attempt - 1))
        elif self.backoff == "linear":
            raw_delay = self.base_delay_seconds * attempt
        else:  # fixed
            raw_delay = self.base_delay_seconds

        capped_delay = min(raw_delay, self.max_delay_seconds)
        if self.jitter:
            return random.uniform(0.5 * capped_delay, capped_delay)
        return capped_delay

    def is_retryable(self, error: Exception | str) -> bool:
        """Classify whether the given error string or exception is retryable."""
        if isinstance(error, Exception):
            err_type = type(error).__name__.upper()
            err_str = (err_type + " " + str(error)).upper()
        else:
            err_str = str(error).upper()

        # Check explicit non-retryable first
        for non_ret in self.non_retryable_errors:
            if non_ret.upper() in err_str:
                logger.debug(
                    "Error '{}' classified as NON-RETRYABLE due to rule '{}'", err_str, non_ret
                )
                return False

        # Check retryable
        for ret in self.retryable_errors:
            if ret.upper() in err_str:
                logger.debug("Error '{}' classified as RETRYABLE due to rule '{}'", err_str, ret)
                return True

        # Default: if it contains timeout or network, retryable; otherwise False
        if any(term in err_str for term in ("TIMEOUT", "NETWORK", "TRANSIENT")):
            return True

        return False

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DurableRetryPolicy:
        """Instantiate DurableRetryPolicy from a dictionary configuration."""
        retry_config = data.get("retry", data)
        return cls(
            max_attempts=int(retry_config.get("max_attempts", 3)),
            backoff=str(retry_config.get("backoff", "exponential")).lower(),
            base_delay_seconds=float(retry_config.get("base_delay_seconds", 1.0)),
            max_delay_seconds=float(retry_config.get("max_delay_seconds", 60.0)),
            backoff_factor=float(retry_config.get("backoff_factor", 2.0)),
            jitter=bool(retry_config.get("jitter", True)),
            retryable_errors=tuple(retry_config.get("retryable_errors", DEFAULT_RETRYABLE_ERRORS)),
            non_retryable_errors=tuple(
                retry_config.get("non_retryable_errors", DEFAULT_NON_RETRYABLE_ERRORS)
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize configuration to a dictionary."""
        return {
            "max_attempts": self.max_attempts,
            "backoff": self.backoff,
            "base_delay_seconds": self.base_delay_seconds,
            "max_delay_seconds": self.max_delay_seconds,
            "backoff_factor": self.backoff_factor,
            "jitter": self.jitter,
            "retryable_errors": list(self.retryable_errors),
            "non_retryable_errors": list(self.non_retryable_errors),
        }
