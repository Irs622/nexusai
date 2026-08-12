"""JSON structured logger with automatic secret redaction."""

from __future__ import annotations

import json
import time
from typing import Any

from nexusai.brain.ports.observability_port import IStructuredLogger
from nexusai.infrastructure.observability.redaction import sanitize_secrets_recursive


class JSONStructuredLogger(IStructuredLogger):
    """Production-grade JSON structured logger enforcing secret redaction before serialization."""

    def __init__(self) -> None:
        self.logs: list[dict[str, Any]] = []

    def info(self, event: str, **kwargs: Any) -> None:
        sanitized_kwargs = sanitize_secrets_recursive(kwargs)
        payload = {
            "timestamp": time.time(),
            "level": "INFO",
            "event": event,
            **sanitized_kwargs,
        }
        self.logs.append(payload)

    def error(self, event: str, **kwargs: Any) -> None:
        sanitized_kwargs = sanitize_secrets_recursive(kwargs)
        payload = {
            "timestamp": time.time(),
            "level": "ERROR",
            "event": event,
            **sanitized_kwargs,
        }
        self.logs.append(payload)
