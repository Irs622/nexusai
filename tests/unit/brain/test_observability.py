"""Unit tests for P2-4 domain observability models, secret sanitization, and event taxonomy."""

from __future__ import annotations

import time
import pytest

from nexusai.brain.domain.observability import (
    RuntimeEvent,
    RuntimeEventType,
    sanitize_attributes,
)


def test_runtime_event_creation_and_immutability() -> None:
    """Test RuntimeEvent dataclass creation and immutability."""
    event = RuntimeEvent(
        event_id="evt-100",
        event_type=RuntimeEventType.NODE_COMPLETED,
        execution_id="exec-1",
        node_id="node-1",
        task_id="task-1",
        attempt=1,
        attributes={"duration_ms": 45.2},
    )

    assert event.event_id == "evt-100"
    assert event.event_type == RuntimeEventType.NODE_COMPLETED
    assert event.execution_id == "exec-1"
    assert event.attributes["duration_ms"] == 45.2

    with pytest.raises(AttributeError):
        event.execution_id = "exec-modified"  # type: ignore[misc]


def test_secret_sanitization_in_attributes() -> None:
    """Test secret hygiene: Passwords, tokens, API keys, and authorization headers are redacted."""
    raw_attrs = {
        "tool_name": "execute_terminal",
        "api_key": "secret-key-12345",
        "authorization": "Bearer token-abc",
        "password": "my-secret-password",
        "duration_ms": 12.5,
    }

    sanitized = sanitize_attributes(raw_attrs)

    assert sanitized["tool_name"] == "execute_terminal"
    assert sanitized["duration_ms"] == 12.5
    assert sanitized["api_key"] == "[REDACTED_SECRET]"
    assert sanitized["authorization"] == "[REDACTED_SECRET]"
    assert sanitized["password"] == "[REDACTED_SECRET]"


if __name__ == "__main__":
    test_runtime_event_creation_and_immutability()
    test_secret_sanitization_in_attributes()
    print("ALL P2-4 OBSERVABILITY DOMAIN UNIT TESTS PASSED SUCCESSFULLY!")
