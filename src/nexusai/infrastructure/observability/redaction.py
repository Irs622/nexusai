"""Centralized recursive secret sanitization and privacy hashing for P4-7 Observability."""

from __future__ import annotations

import hashlib
import json
from typing import Any

SENSITIVE_KEY_PATTERNS = frozenset({
    "api_key",
    "access_token",
    "refresh_token",
    "authorization",
    "cookie",
    "password",
    "secret",
    "private_key",
    "bearer",
    "credential",
    "token",
})


def sanitize_secrets_recursive(data: Any) -> Any:
    """Recursively sanitize sensitive keys in nested dicts, lists, and tuples."""
    if isinstance(data, dict):
        sanitized_dict = {}
        for k, v in data.items():
            k_str = str(k).lower()
            if any(pattern in k_str for pattern in SENSITIVE_KEY_PATTERNS):
                sanitized_dict[k] = "[REDACTED_SECRET]"
            else:
                sanitized_dict[k] = sanitize_secrets_recursive(v)
        return sanitized_dict
    elif isinstance(data, (list, tuple)):
        return type(data)([sanitize_secrets_recursive(item) for item in data])
    elif isinstance(data, str):
        # Redact raw Bearer tokens or key- strings
        if "bearer " in data.lower() or "key-" in data.lower():
            return "[REDACTED_SECRET_STRING]"
        return data
    else:
        return data


def hash_content_summary(content: str) -> str:
    """Compute a deterministic SHA-256 hash summary for LLM prompt/response or tool arguments."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()
