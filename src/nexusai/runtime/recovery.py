"""Startup Crash Recovery Protocol for discovering stale worker executions and recovering with fencing tokens."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from nexusai.brain.domain.execution_coordination import ExecutionLease, WorkerIdentity
from nexusai.brain.ports.execution_coordinator_port import IExecutionCoordinator
from nexusai.core.annotations import stable
from nexusai.infrastructure.persistence.sqlite_execution_store import SQLiteExecutionStateStore
from nexusai.logging.logger import logger
from nexusai.runtime.execution_engine import DurableExecutionEngine, DurableExecutionState


@stable
@dataclass
class RecoveryReport:
    """Summary metrics of a startup crash recovery execution."""

    total_scanned: int = 0
    reclaimed_count: int = 0
    skipped_active_count: int = 0
    cancelled_count: int = 0
    terminal_failed_count: int = 0
    recovered_execution_ids: list[str] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)


@stable
class CrashRecoveryProtocol:
    """Startup recovery protocol querying execution store for stale executions and reclaiming expired worker leases."""

    def __init__(
        self,
        store: SQLiteExecutionStateStore,
        coordinator: IExecutionCoordinator,
        engine: DurableExecutionEngine | None = None,
        worker_identity: WorkerIdentity | None = None,
        max_retries: int = 3,
    ) -> None:
        self.store = store
        self.coordinator = coordinator
        self.engine = engine
        self.worker = worker_identity or WorkerIdentity(worker_id="worker-recovery-01")
        self.max_retries = max_retries

    async def run_startup_recovery(self) -> RecoveryReport:
        """Scan durable store for interrupted executions and recover orphaned leases with monotonically higher fencing tokens."""
        logger.info("CrashRecoveryProtocol: Starting scan for interrupted executions...")

        report = RecoveryReport()
        stale_records = await self.store.get_stale_or_running_executions(
            states=[
                DurableExecutionState.RUNNING.value,
                DurableExecutionState.QUEUED.value,
                DurableExecutionState.CHECKPOINT.value,
                DurableExecutionState.FAILED_RETRYABLE.value,
            ]
        )
        report.total_scanned = len(stale_records)

        now = time.time()
        for record in stale_records:
            exec_id = record.execution_id
            logger.info(
                "Inspecting stale execution {} (status: {})...", exec_id, record.status.value
            )

            # 1. Check if execution was cancelled
            if await self.store.is_cancellation_requested(exec_id):
                logger.info("Execution {} was cancelled; finalizing status to CANCELLED", exec_id)
                await self.store.record_state_transition(
                    execution_id=exec_id,
                    from_state=record.status.value,
                    to_state=DurableExecutionState.CANCELLED.value,
                    actor="recovery-protocol",
                    worker_id=self.worker.worker_id,
                    fencing_token=record.fencing_token or 1,
                    reason="Durable cancellation finalized by startup recovery protocol",
                )
                report.cancelled_count += 1
                continue

            # 2. Check current worker lease
            lease: ExecutionLease | None = await self.coordinator.get_current_lease(exec_id)

            if (
                lease is not None
                and lease.expires_at > now
                and lease.worker_id != self.worker.worker_id
            ):
                # Active lease held by another living worker
                logger.info(
                    "Execution {} is actively leased to worker '{}' (expires in {:.1f}s), skipping",
                    exec_id,
                    lease.worker_id,
                    lease.expires_at - now,
                )
                report.skipped_active_count += 1
                continue

            # 3. Lease is expired or unowned
            if record.retry_count >= self.max_retries:
                logger.warning(
                    "Execution {} exceeded max recovery attempts ({}/{}), marking FAILED_TERMINAL",
                    exec_id,
                    record.retry_count,
                    self.max_retries,
                )
                token = lease.fencing_token if lease else (record.fencing_token or 1)
                await self.store.record_state_transition(
                    execution_id=exec_id,
                    from_state=record.status.value,
                    to_state=DurableExecutionState.FAILED_TERMINAL.value,
                    actor="recovery-protocol",
                    worker_id=self.worker.worker_id,
                    fencing_token=token,
                    reason=f"Exceeded max retries ({self.max_retries}) during crash recovery",
                )
                report.terminal_failed_count += 1
                continue

            # 4. Recover expired lease with higher fencing token
            try:
                new_lease = await self.coordinator.recover_expired_execution_lease(
                    execution_id=exec_id,
                    new_worker=self.worker,
                    ttl_seconds=60.0,
                )
                new_token = new_lease.fencing_token
                logger.info(
                    "Recovered expired lease for execution {} with new fencing token {}",
                    exec_id,
                    new_token,
                )

                # Transition to FAILED_RETRYABLE so it can be picked up or retried
                await self.store.record_state_transition(
                    execution_id=exec_id,
                    from_state=record.status.value,
                    to_state=DurableExecutionState.FAILED_RETRYABLE.value,
                    actor="recovery-protocol",
                    worker_id=self.worker.worker_id,
                    fencing_token=new_token,
                    reason=f"Recovered from crashed worker with fencing token {new_token}",
                )

                report.reclaimed_count += 1
                report.recovered_execution_ids.append(exec_id)

            except Exception as rec_err:
                logger.error("Failed to recover lease for execution {}: {}", exec_id, rec_err)

        logger.info(
            "CrashRecoveryProtocol completed: scanned={}, reclaimed={}, skipped={}, cancelled={}, terminal_failed={}",
            report.total_scanned,
            report.reclaimed_count,
            report.skipped_active_count,
            report.cancelled_count,
            report.terminal_failed_count,
        )
        return report
