"""AuditService runtime component providing safe query, timeline reconstruction, and verification API."""

from __future__ import annotations

from typing import Any, Sequence

from nexusai.brain.domain.audit import (
    AuditEvent,
    AuditEventType,
    AuditPrivacyLevel,
    AuditVerificationResult,
)
from nexusai.brain.ports.audit_store_port import IAuditStore


class AuditService:
    """High-level audit service executing non-authoritative evidence recording and tamper-evident chain verification."""

    def __init__(
        self,
        audit_store: IAuditStore,
        privacy_level: AuditPrivacyLevel = AuditPrivacyLevel.AUDIT_STANDARD,
    ) -> None:
        self.audit_store = audit_store
        self.privacy_level = privacy_level

    async def record_event(
        self,
        event_type: AuditEventType | str,
        session_id: str,
        execution_id: str,
        plan_fingerprint: str,
        event_id: str = "",
        node_id: str | None = None,
        tool_id: str | None = None,
        worker_id: str | None = None,
        fencing_token: int | None = None,
        actor: str | None = None,
        outcome: str = "SUCCESS",
        severity: str = "INFO",
        metadata: dict[str, Any] | None = None,
    ) -> AuditEvent:
        """Construct and durably append a correlated audit event with hash chaining."""
        evt_type = event_type.value if isinstance(event_type, AuditEventType) else str(event_type)
        if not event_id:
            import time
            event_id = f"evt-{execution_id}-{int(time.time() * 1000)}"

        event = AuditEvent(
            event_id=event_id,
            event_type=evt_type,
            session_id=session_id,
            execution_id=execution_id,
            plan_fingerprint=plan_fingerprint,
            sequence_number=0,  # Auto-allocated by store
            node_id=node_id,
            tool_id=tool_id,
            worker_id=worker_id,
            fencing_token=fencing_token,
            actor=actor,
            outcome=outcome,
            severity=severity,
            metadata=metadata or {},
        )
        return await self.audit_store.append_event(event)

    async def verify_execution_audit(self, execution_id: str) -> AuditVerificationResult:
        """Perform tamper-evident hash chain and correlation verification for execution_id."""
        return await self.audit_store.verify_chain(execution_id)

    async def reconstruct_execution_timeline(self, execution_id: str) -> Sequence[AuditEvent]:
        """Reconstruct chronological audit timeline for an execution."""
        return await self.audit_store.get_events(execution_id)
