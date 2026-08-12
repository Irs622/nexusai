"""CrashRecoveryManager runtime implementing crash recovery classification, orphaned reservation cleanup, and fail-closed safety."""

from __future__ import annotations

import time
from typing import Any, Sequence

from nexusai.brain.domain.execution_recovery import (
    JournalEntry,
    JournalLifecyclePhase,
    RecoveryStatus,
    TERMINAL_JOURNAL_PHASES,
)
from nexusai.brain.domain.observability import RuntimeEvent, RuntimeEventType
from nexusai.brain.domain.tool_registry import ToolIdempotency
from nexusai.brain.ports.execution_recovery_port import IExecutionJournal
from nexusai.brain.ports.governance_port import IGovernancePort
from nexusai.brain.ports.human_approval_port import IHumanApprovalPort
from nexusai.brain.ports.observability_port import IObservabilityPort
from nexusai.brain.ports.tool_registry_port import IToolRegistry


class CrashRecoveryManager:
    """Orchestration recovery manager classifying interrupted executions and enforcing fail-closed recovery policies."""

    def __init__(

        self,
        journal: IExecutionJournal,
        governance: IGovernancePort | None = None,
        approval_engine: IHumanApprovalPort | None = None,
        tool_registry: IToolRegistry | None = None,
        telemetry: IObservabilityPort | None = None,
    ) -> None:
        self.journal = journal
        self.governance = governance
        self.approval_engine = approval_engine
        self.tool_registry = tool_registry
        self.telemetry = telemetry

    def classify_execution_phase(self, entry: JournalEntry) -> RecoveryStatus:
        """Deterministically classify recovery status based on durable journal phase and tool idempotency."""
        if entry.phase in TERMINAL_JOURNAL_PHASES:
            return RecoveryStatus.NON_RECOVERABLE

        if entry.phase in (
            JournalLifecyclePhase.CREATED,
            JournalLifecyclePhase.PLANNING,
            JournalLifecyclePhase.PLAN_VALIDATED,
            JournalLifecyclePhase.WAITING_APPROVAL,
        ):
            return RecoveryStatus.RECOVERABLE

        if entry.phase in (
            JournalLifecyclePhase.APPROVED,
            JournalLifecyclePhase.GOVERNANCE_RESERVED,
            JournalLifecyclePhase.READY_TO_EXECUTE,
        ):
            return RecoveryStatus.RECOVERABLE_WITH_REVALIDATION

        if entry.phase == JournalLifecyclePhase.EXECUTING_TOOL:
            # P4-5-INV-13: Non-idempotent or unknown tools during ambiguous crash fail closed!
            if entry.idempotency == ToolIdempotency.IDEMPOTENT:
                return RecoveryStatus.RECOVERABLE_WITH_REVALIDATION
            return RecoveryStatus.AMBIGUOUS_SIDE_EFFECT

        if entry.phase in (
            JournalLifecyclePhase.TOOL_EXECUTED,
            JournalLifecyclePhase.OBSERVATION_PENDING,
            JournalLifecyclePhase.OBSERVATION_PERSISTED,
            JournalLifecyclePhase.MEMORY_PENDING,
            JournalLifecyclePhase.MEMORY_PERSISTED,
        ):
            return RecoveryStatus.RECOVERABLE_WITH_REVALIDATION

        return RecoveryStatus.AMBIGUOUS_SIDE_EFFECT

    async def recover_execution(self, execution_id: str) -> RecoveryStatus:
        """Perform crash recovery for execution_id enforcing complete security re-validation."""
        latest = await self.journal.get_latest_entry(execution_id)
        if not latest:
            return RecoveryStatus.NON_RECOVERABLE

        status = self.classify_execution_phase(latest)

        # Ambiguous side effect or non-recoverable phases fail closed
        if status in (RecoveryStatus.AMBIGUOUS_SIDE_EFFECT, RecoveryStatus.NON_RECOVERABLE):
            await self._fail_closed(latest, reason=f"Recovery classification {status.value}")
            return status

        # Re-validation of ToolRegistry & Governance if recoverable with revalidation
        if status == RecoveryStatus.RECOVERABLE_WITH_REVALIDATION:
            if self.tool_registry and latest.tool_id:
                try:
                    await self.tool_registry.validate_tool(latest.tool_id)
                except Exception as err:
                    await self._fail_closed(latest, reason=f"ToolRegistry re-validation failed: {err}")
                    return RecoveryStatus.NON_RECOVERABLE

            if self.governance and latest.governance_reservation_id:
                # Release orphaned governance reservation
                try:
                    await self.governance.release(latest.governance_reservation_id)
                except Exception:
                    pass

        # Append recovery resume journal entry
        now = time.time()
        recovery_entry = JournalEntry(
            entry_id=f"rec-{execution_id}-{int(now * 1000)}",
            session_id=latest.session_id,
            execution_id=latest.execution_id,
            plan_fingerprint=latest.plan_fingerprint,
            node_id=latest.node_id,
            tool_id=latest.tool_id,
            action_digest=latest.action_digest,
            phase=latest.phase,
            timestamp=now,
            attempt=latest.attempt + 1,
            recovery_status=status,
            metadata={"recovered_from_phase": latest.phase.value},
        )
        await self.journal.append_entry(recovery_entry)
        await self._safe_telemetry(latest, status)
        return status

    async def recover_all_active(self) -> dict[str, RecoveryStatus]:
        """Discover and recover all active non-terminal executions upon startup."""
        active_ids = await self.journal.get_active_executions()
        results = {}
        for exec_id in active_ids:
            results[exec_id] = await self.recover_execution(exec_id)
        return results

    async def _fail_closed(self, latest: JournalEntry, reason: str) -> None:
        """Transition execution to ABANDONED phase and release orphaned governance reservations."""
        now = time.time()
        abandon_entry = JournalEntry(
            entry_id=f"abnd-{latest.execution_id}-{int(now * 1000)}",
            session_id=latest.session_id,
            execution_id=latest.execution_id,
            plan_fingerprint=latest.plan_fingerprint,
            node_id=latest.node_id,
            tool_id=latest.tool_id,
            action_digest=latest.action_digest,
            phase=JournalLifecyclePhase.ABANDONED,
            timestamp=now,
            attempt=latest.attempt,
            recovery_status=RecoveryStatus.AMBIGUOUS_SIDE_EFFECT,
            metadata={"reason": reason},
        )
        await self.journal.append_entry(abandon_entry)

        if self.governance and latest.governance_reservation_id:
            try:
                await self.governance.release(latest.governance_reservation_id)
            except Exception:
                pass

        if self.approval_engine:
            try:
                await self.approval_engine.cancel_pending_requests(latest.execution_id)
            except Exception:
                pass

    async def _safe_telemetry(self, entry: JournalEntry, status: RecoveryStatus) -> None:
        if not self.telemetry:
            return
        try:
            now = time.time()
            evt = RuntimeEvent(
                event_id=f"rec-evt-{int(now * 1000)}",
                event_type=RuntimeEventType.EXECUTION_STARTED,
                timestamp=now,
                execution_id=entry.execution_id,
                attributes={
                    "session_id": entry.session_id,
                    "recovery_status": status.value,
                    "phase": entry.phase.value,
                },
            )
            await self.telemetry.emit_event(evt)
        except Exception:
            pass
