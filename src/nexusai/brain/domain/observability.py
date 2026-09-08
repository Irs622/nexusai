"""Domain observability models, event taxonomy, correlation context, and secret hygiene utilities."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping


class RuntimeEventType(str, Enum):
    """Domain taxonomy for observable runtime events."""

    EXECUTION_STARTED = "EXECUTION_STARTED"
    EXECUTION_COMPLETED = "EXECUTION_COMPLETED"
    EXECUTION_FAILED = "EXECUTION_FAILED"
    EXECUTION_CANCELLED = "EXECUTION_CANCELLED"

    PLANNING_STARTED = "PLANNING_STARTED"
    PLANNING_COMPLETED = "PLANNING_COMPLETED"

    NODE_SUBMITTED = "NODE_SUBMITTED"
    NODE_CLAIMED = "NODE_CLAIMED"
    NODE_STARTED = "NODE_STARTED"
    NODE_COMPLETED = "NODE_COMPLETED"
    NODE_FAILED = "NODE_FAILED"
    NODE_CANCELLED = "NODE_CANCELLED"

    TOOL_STARTED = "TOOL_STARTED"
    TOOL_COMPLETED = "TOOL_COMPLETED"
    TOOL_FAILED = "TOOL_FAILED"
    TOOL_TIMEOUT = "TOOL_TIMEOUT"
    TOOL_CANCELLED = "TOOL_CANCELLED"

    RECOVERY_CLASSIFIED = "RECOVERY_CLASSIFIED"
    RECOVERY_RETRY = "RECOVERY_RETRY"
    RECOVERY_RECONCILIATION_REQUIRED = "RECOVERY_RECONCILIATION_REQUIRED"
    RECOVERY_RECONCILIATION_COMPLETED = "RECOVERY_RECONCILIATION_COMPLETED"
    RECOVERY_FAILED = "RECOVERY_FAILED"

    CHECKPOINT_STARTED = "CHECKPOINT_STARTED"
    CHECKPOINT_COMPLETED = "CHECKPOINT_COMPLETED"
    CHECKPOINT_FAILED = "CHECKPOINT_FAILED"

    SCHEDULER_SUBMITTED = "SCHEDULER_SUBMITTED"
    SCHEDULER_CLAIMED = "SCHEDULER_CLAIMED"
    SCHEDULER_CANCELLED = "SCHEDULER_CANCELLED"
    SCHEDULER_REJECTED = "SCHEDULER_REJECTED"
    SCHEDULER_SHUTDOWN = "SCHEDULER_SHUTDOWN"

    CIRCUIT_BREAKER_OPEN = "CIRCUIT_BREAKER_OPEN"
    CIRCUIT_BREAKER_HALF_OPEN = "CIRCUIT_BREAKER_HALF_OPEN"
    CIRCUIT_BREAKER_CLOSED = "CIRCUIT_BREAKER_CLOSED"

    GOVERNANCE_AUTHORIZED = "GOVERNANCE_AUTHORIZED"
    GOVERNANCE_DENIED = "GOVERNANCE_DENIED"
    RESOURCE_RESERVED = "RESOURCE_RESERVED"
    RESOURCE_RESERVATION_REJECTED = "RESOURCE_RESERVATION_REJECTED"
    RESOURCE_RELEASED = "RESOURCE_RELEASED"
    RESOURCE_QUOTA_EXCEEDED = "RESOURCE_QUOTA_EXCEEDED"
    CAPABILITY_DENIED = "CAPABILITY_DENIED"


# Sensitive keys forbidden from telemetry attributes
FORBIDDEN_SECRET_KEYS = {
    "password",
    "secret",
    "token",
    "api_key",
    "apikey",
    "authorization",
    "private_key",
    "credential",
    "bearer",
}


def _is_secret_key(key: str) -> bool:
    low = key.lower()
    if any(k in low for k in FORBIDDEN_SECRET_KEYS):
        return True
    if low == "auth" or low.startswith("auth_") or low.endswith("_auth") or "_auth_" in low:
        return True
    return False


def sanitize_attributes(attributes: Mapping[str, Any] | None) -> dict[str, Any]:
    """Sanitize attributes dictionary to prevent secrets or credentials from leaking into telemetry."""
    if not attributes:
        return {}

    sanitized: dict[str, Any] = {}
    for key, val in attributes.items():
        if _is_secret_key(str(key)):
            sanitized[key] = "[REDACTED_SECRET]"
        elif isinstance(val, (int, float, bool, str)):
            sanitized[key] = val
        else:
            sanitized[key] = str(val)[:200]
    return sanitized


@dataclass(frozen=True)
class RuntimeEvent:
    """Immutable domain representation of a correlated runtime event."""

    event_id: str
    event_type: RuntimeEventType
    timestamp: float = field(default_factory=time.time)
    execution_id: str | None = None
    node_id: str | None = None
    task_id: str | None = None
    attempt: int | None = None
    attributes: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Enforce attribute secret sanitization
        sanitized = sanitize_attributes(self.attributes)
        object.__setattr__(self, "attributes", sanitized)
