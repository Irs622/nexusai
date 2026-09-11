"""IIdempotencyPort interface decoupling execution engines from durable idempotency storage."""

from __future__ import annotations

from typing import Any, Protocol


class IIdempotencyPort(Protocol):
    """Abstract port for identity-scoped execution idempotency."""

    async def start_execution(
        self,
        tenant_id: str,
        user_id: str,
        idempotency_key: str,
        fingerprint: str,
        ttl_seconds: float = 86400.0,
    ) -> tuple[Any, bool]:
        """Start or retrieve an execution record for the given scoped idempotency key."""
        ...

    async def complete_execution(
        self,
        tenant_id: str,
        user_id: str,
        idempotency_key: str,
        response: dict[str, Any],
    ) -> Any:
        """Mark execution as SUCCEEDED, sanitizing and caching the output."""
        ...

    async def fail_execution(
        self,
        tenant_id: str,
        user_id: str,
        idempotency_key: str,
        error: Exception | str,
        state: Any | None = None,
    ) -> Any:
        """Mark execution as failed with classified transient or terminal error state."""
        ...
