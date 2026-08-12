"""Unit test suite for centralized recursive secret sanitization."""

from __future__ import annotations

import pytest

from nexusai.infrastructure.observability.redaction import sanitize_secrets_recursive


def test_recursive_secret_redaction() -> None:
    """Test sanitize_secrets_recursive redacts API keys, access tokens, and bearer strings across nested data structures."""
    payload = {
        "user": "alice",
        "api_key": "sk-secret-12345",
        "config": {
            "access_token": "bearer-token-val",
            "db_password": "super-secret-pass",
            "headers": {"Authorization": "Bearer secret-jwt-token"},
        },
        "items": [
            {"credential": "private-key-data"},
            "raw text string containing Bearer secret-val",
        ],
    }

    sanitized = sanitize_secrets_recursive(payload)

    assert sanitized["user"] == "alice"
    assert sanitized["api_key"] == "[REDACTED_SECRET]"
    assert sanitized["config"]["access_token"] == "[REDACTED_SECRET]"
    assert sanitized["config"]["db_password"] == "[REDACTED_SECRET]"
    assert sanitized["config"]["headers"]["Authorization"] == "[REDACTED_SECRET]"
    assert sanitized["items"][0]["credential"] == "[REDACTED_SECRET]"
    assert sanitized["items"][1] == "[REDACTED_SECRET_STRING]"


if __name__ == "__main__":
    test_recursive_secret_redaction()
    print("ALL REDACTION UNIT TESTS PASSED SUCCESSFULLY!")
