"""IAuditStore protocol contract interface for durable, tamper-evident audit log storage."""

from __future__ import annotations

from typing import Protocol, Sequence

from nexusai.brain.domain.audit import AuditEvent, AuditVerificationResult


class IAuditStore(Protocol):
    """Abstract protocol port interface for durable, tamper-evident audit event persistence and verification."""

    async def append_event(self, event: AuditEvent) -> AuditEvent:
        """Atomically append a correlated audit event with tamper-evident SHA-256 hash chaining."""
        ...

    async def get_events(
        self, execution_id: str | None = None, tenant_id: str | None = None
    ) -> Sequence[AuditEvent]:
        """Retrieve full ordered audit history filtered by execution_id and/or tenant_id."""
        ...

    async def get_event(self, event_id: str) -> AuditEvent | None:
        """Retrieve a specific audit event by event_id."""
        ...

    async def get_latest_event(
        self, execution_id: str | None = None, tenant_id: str | None = None
    ) -> AuditEvent | None:
        """Retrieve the most recent audit event for an execution and/or tenant."""
        ...

    async def verify_chain(
        self, execution_id: str | None = None, tenant_id: str | None = None
    ) -> AuditVerificationResult:
        """Verify sequence monotonicity, previous event hash linkages, and SHA-256 payload integrity."""
        ...

    async def startup_integrity_check(
        self, tenant_id: str | None = None
    ) -> AuditVerificationResult:
        """Perform startup integrity verification on existing persistent audit log."""
        ...
