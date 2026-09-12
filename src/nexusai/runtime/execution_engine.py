"""Durable Execution Engine with persistent state machine, worker leases, fencing tokens, checkpointing, and crash recovery."""

from __future__ import annotations

import asyncio
import time
from enum import Enum
from typing import Any, Callable, Coroutine

from nexusai.brain.domain.audit import AuditEvent
from nexusai.brain.domain.execution_coordination import WorkerIdentity
from nexusai.brain.domain.execution_state import (
    ExecutionRecord,
    ExecutionStatus,
    NodeExecutionRecord,
    NodeExecutionStatus,
)
from nexusai.brain.ports.audit_store_port import IAuditStore
from nexusai.brain.ports.execution_coordinator_port import IExecutionCoordinator
from nexusai.core.annotations import stable
from nexusai.infrastructure.persistence.sqlite_execution_store import SQLiteExecutionStateStore
from nexusai.logging.logger import logger
from nexusai.runtime.execution_semantics import ExecutionSemantics
from nexusai.runtime.retry_policy import DurableRetryPolicy
from nexusai.security.guard import RiskLevel


@stable
class DurableExecutionState(str, Enum):
    """Persistent state machine statuses for durable executions."""

    CREATED = "CREATED"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    CHECKPOINT = "CHECKPOINT"
    SUCCEEDED = "SUCCEEDED"
    FAILED_RETRYABLE = "FAILED_RETRYABLE"
    FAILED_TERMINAL = "FAILED_TERMINAL"
    CANCELLED = "CANCELLED"
    TIMED_OUT = "TIMED_OUT"


# Allowed state transition DAG
VALID_DURABLE_TRANSITIONS: dict[str, set[str]] = {
    DurableExecutionState.CREATED.value: {
        DurableExecutionState.QUEUED.value,
        DurableExecutionState.RUNNING.value,
        DurableExecutionState.CANCELLED.value,
    },
    DurableExecutionState.QUEUED.value: {
        DurableExecutionState.RUNNING.value,
        DurableExecutionState.CANCELLED.value,
        DurableExecutionState.TIMED_OUT.value,
    },
    DurableExecutionState.RUNNING.value: {
        DurableExecutionState.CHECKPOINT.value,
        DurableExecutionState.SUCCEEDED.value,
        DurableExecutionState.FAILED_RETRYABLE.value,
        DurableExecutionState.FAILED_TERMINAL.value,
        DurableExecutionState.CANCELLED.value,
        DurableExecutionState.TIMED_OUT.value,
    },
    DurableExecutionState.CHECKPOINT.value: {
        DurableExecutionState.QUEUED.value,
        DurableExecutionState.RUNNING.value,
        DurableExecutionState.CHECKPOINT.value,
        DurableExecutionState.SUCCEEDED.value,
        DurableExecutionState.FAILED_RETRYABLE.value,
        DurableExecutionState.FAILED_TERMINAL.value,
        DurableExecutionState.CANCELLED.value,
        DurableExecutionState.TIMED_OUT.value,
    },
    DurableExecutionState.FAILED_RETRYABLE.value: {
        DurableExecutionState.QUEUED.value,
        DurableExecutionState.RUNNING.value,
        DurableExecutionState.FAILED_TERMINAL.value,
        DurableExecutionState.CANCELLED.value,
    },
    DurableExecutionState.SUCCEEDED.value: set(),
    DurableExecutionState.FAILED_TERMINAL.value: set(),
    DurableExecutionState.CANCELLED.value: set(),
    DurableExecutionState.TIMED_OUT.value: set(),
}


class InvalidStateTransitionError(ValueError):
    """Raised when an illegal state machine transition is attempted."""

    pass


class ApprovalRequiredError(RuntimeError):
    """Raised when an at_least_once tool with high risk requires human approval prior to retry."""

    pass


@stable
class DurableExecutionEngine:
    """Authoritative durable execution engine enforcing state persistence, leases, fencing tokens, and checkpoint recovery."""

    def __init__(
        self,
        store: SQLiteExecutionStateStore,
        coordinator: IExecutionCoordinator,
        audit_store: IAuditStore | None = None,
        default_retry_policy: DurableRetryPolicy | None = None,
        worker_identity: WorkerIdentity | None = None,
        tool_registry: Any | None = None,
        journal: Any | None = None,
    ) -> None:
        self.store = store
        self.coordinator = coordinator
        self.audit_store = audit_store
        self.default_retry_policy = default_retry_policy or DurableRetryPolicy()
        self.worker = worker_identity or WorkerIdentity(worker_id="worker-local-01")
        self.tool_registry = tool_registry
        self.journal = journal
        self._active_tasks: dict[str, asyncio.Task[Any]] = {}

    async def _transition_state(
        self,
        execution_id: str,
        to_state: DurableExecutionState | str,
        fencing_token: int,
        actor: str = "system",
        reason: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """Atomically transition execution state with fencing token and transition matrix validation."""
        target_val = (
            to_state.value if isinstance(to_state, DurableExecutionState) else str(to_state)
        )

        record = await self.store.load_execution(execution_id)
        current_status = record.status.value if record else DurableExecutionState.CREATED.value

        # Idempotency: same state is no-op
        if current_status == target_val:
            return True

        # Validate transition matrix
        allowed_targets = VALID_DURABLE_TRANSITIONS.get(current_status, set())
        if target_val not in allowed_targets:
            raise InvalidStateTransitionError(
                f"Invalid execution state transition: {current_status} -> {target_val} for execution '{execution_id}'"
            )

        success = await self.store.record_state_transition(
            execution_id=execution_id,
            from_state=current_status,
            to_state=target_val,
            actor=actor,
            worker_id=self.worker.worker_id,
            fencing_token=fencing_token,
            reason=reason,
            metadata=metadata,
        )

        logger.info(
            "Durable execution {} transition: {} -> {} (token={}, actor={})",
            execution_id,
            current_status,
            target_val,
            fencing_token,
            actor,
        )

        if self.audit_store:
            try:
                evt = AuditEvent(
                    event_id=f"audit-trans-{execution_id}-{time.time_ns()}-{fencing_token}",
                    event_type="EXECUTION_STATE_TRANSITION",
                    session_id=record.plan_id if record else "session-durable",
                    execution_id=execution_id,
                    plan_fingerprint=record.graph_hash if record else "fp-none",
                    sequence_number=0,
                    timestamp=time.time(),
                    actor=actor,
                    tenant_id=record.tenant_id if record else "default",
                    outcome="SUCCESS",
                    severity="INFO",
                    fencing_token=fencing_token,
                    metadata={
                        "from_state": current_status,
                        "to_state": target_val,
                        "worker_id": self.worker.worker_id,
                        "reason": reason,
                    },
                )
                await self.audit_store.append_event(evt)
            except Exception as audit_err:
                logger.warning("Failed to record state transition audit event: {}", audit_err)

        if self.journal and hasattr(self.journal, "record_durable_state_transition"):
            try:
                await self.journal.record_durable_state_transition(
                    execution_id=execution_id,
                    from_state=current_status,
                    to_state=target_val,
                    actor=actor,
                    worker_id=self.worker.worker_id,
                    fencing_token=fencing_token,
                    reason=reason,
                    metadata=metadata,
                )
            except Exception as j_err:
                logger.debug("Failed to record durable state journal transition: {}", j_err)

        return success

    async def execute_dag(
        self,
        execution_id: str,
        plan_id: str,
        nodes: list[dict[str, Any]],
        step_executor: Callable[[dict[str, Any], int], Coroutine[Any, Any, Any]],
        actor: str = "system",
        tenant_id: str = "default",
        retry_policy: DurableRetryPolicy | None = None,
        lease_ttl_seconds: float = 30.0,
    ) -> dict[str, Any]:
        """Execute a multi-step DAG durably with checkpointing, fencing tokens, and crash recovery."""
        policy = retry_policy or self.default_retry_policy

        # 1. Check if execution record already exists in store
        record = await self.store.load_execution(execution_id)
        if record is None:
            node_records = {}
            for idx, n in enumerate(nodes):
                nid = str(n.get("id", idx + 1))
                node_records[nid] = NodeExecutionRecord(
                    execution_id=execution_id,
                    node_id=nid,
                    status=NodeExecutionStatus.PENDING,
                    tool_name=str(n.get("tool", "tool")),
                    arguments=n.get("arguments", {}),
                )

            record = ExecutionRecord(
                execution_id=execution_id,
                plan_id=plan_id,
                graph_hash=f"hash-{plan_id}",
                status=ExecutionStatus.CREATED,
                schema_version=3,
                node_records=node_records,
                worker_id=self.worker.worker_id,
                actor=actor,
                tenant_id=tenant_id,
            )
            await self.store.create_execution(record)

        # 2. Acquire Worker Lease & Fencing Token
        lease = await self.coordinator.acquire_execution_lease(
            execution_id=execution_id,
            session_id=plan_id,
            worker=self.worker,
            ttl_seconds=lease_ttl_seconds,
        )
        fencing_token = lease.fencing_token

        # 3. Transitions: CREATED -> QUEUED -> RUNNING
        await self._transition_state(
            execution_id,
            DurableExecutionState.QUEUED,
            fencing_token,
            actor=actor,
            reason="Queued for durable execution",
        )

        await self._transition_state(
            execution_id,
            DurableExecutionState.RUNNING,
            fencing_token,
            actor=actor,
            reason=f"Acquired lease {lease.lease_id}",
        )

        completed_outputs: dict[str, Any] = {}

        try:
            # 4. Step-by-step execution with checkpointing
            for idx, node in enumerate(nodes):
                node_id = str(node.get("id", idx + 1))
                tool_name = str(node.get("tool", "unknown_tool"))

                # Check cancellation
                if await self.store.is_cancellation_requested(execution_id):
                    await self._transition_state(
                        execution_id,
                        DurableExecutionState.CANCELLED,
                        fencing_token,
                        actor=actor,
                        reason="Cancellation requested",
                    )
                    return {
                        "status": DurableExecutionState.CANCELLED.value,
                        "execution_id": execution_id,
                        "completed_steps": list(completed_outputs.keys()),
                    }

                # Check if node was already completed in durable store (resume scenario!)
                existing_node = record.node_records.get(node_id) or (
                    record.node_records.get(int(node_id)) if str(node_id).isdigit() else None
                )
                if existing_node and existing_node.status == NodeExecutionStatus.COMPLETED:
                    logger.info(
                        "Resuming DAG {}: skipping already completed step {}", execution_id, node_id
                    )
                    completed_outputs[node_id] = existing_node.output
                    continue

                # Mark node RUNNING
                await self.store.mark_node_running(execution_id, node_id)

                # Execute step with retry policy & side-effect semantics
                step_result = await self._execute_step_with_retries(
                    execution_id=execution_id,
                    node=node,
                    node_id=node_id,
                    fencing_token=fencing_token,
                    step_executor=step_executor,
                    policy=policy,
                    actor=actor,
                )

                completed_outputs[node_id] = step_result

                # Checkpoint after each completed step
                await self._transition_state(
                    execution_id,
                    DurableExecutionState.CHECKPOINT,
                    fencing_token,
                    actor=actor,
                    reason=f"Step {node_id} completed",
                    metadata={"step_id": node_id, "tool": tool_name},
                )

            # 5. All steps completed -> SUCCEEDED
            await self._transition_state(
                execution_id,
                DurableExecutionState.SUCCEEDED,
                fencing_token,
                actor=actor,
                reason="All DAG steps executed successfully",
            )
            return {
                "status": DurableExecutionState.SUCCEEDED.value,
                "execution_id": execution_id,
                "outputs": completed_outputs,
            }

        except asyncio.CancelledError:
            await self._transition_state(
                execution_id,
                DurableExecutionState.CANCELLED,
                fencing_token,
                actor=actor,
                reason="Task cancelled",
            )
            return {
                "status": DurableExecutionState.CANCELLED.value,
                "execution_id": execution_id,
                "completed_steps": list(completed_outputs.keys()),
            }

        except Exception as err:
            logger.error("Durable execution {} failed: {}", execution_id, err)
            is_retryable = policy.is_retryable(err)
            terminal_state = (
                DurableExecutionState.FAILED_RETRYABLE
                if is_retryable
                else DurableExecutionState.FAILED_TERMINAL
            )
            await self._transition_state(
                execution_id,
                terminal_state,
                fencing_token,
                actor=actor,
                reason=f"Failure: {err}",
            )
            raise

        finally:
            try:
                await self.coordinator.release_execution_lease(lease.lease_id, self.worker)
            except Exception as rel_err:
                logger.debug("Lease release: {}", rel_err)

    async def _execute_step_with_retries(
        self,
        execution_id: str,
        node: dict[str, Any],
        node_id: str,
        fencing_token: int,
        step_executor: Callable[[dict[str, Any], int], Coroutine[Any, Any, Any]],
        policy: DurableRetryPolicy,
        actor: str,
    ) -> Any:
        """Execute a single step with error classification, exponential backoff, and semantics checks."""
        from nexusai.brain.ports.tool_port import ToolExecutionResult

        # Security constraint: execution_semantics MUST NOT be user-configurable at request time.
        # The value comes exclusively from the tool class declaration, plugin manifest,
        # or policy administrator configuration. A client MUST NOT be able to send
        # {"execution_semantics": "idempotent"} to force automatic retry on an at_least_once tool.
        tool_name = str(node.get("tool", ""))
        tool_instance = None
        if self.tool_registry:
            if hasattr(self.tool_registry, "has_tool") and self.tool_registry.has_tool(tool_name):
                tool_instance = self.tool_registry.get(tool_name)
            elif hasattr(self.tool_registry, "get"):
                try:
                    tool_instance = self.tool_registry.get(tool_name)
                except Exception:
                    pass

        if tool_instance is not None:
            tool_semantics = getattr(
                tool_instance, "execution_semantics", ExecutionSemantics.AT_LEAST_ONCE
            )
            risk_level = getattr(tool_instance, "risk_level", RiskLevel.LOW)
        else:
            raw_semantics = node.get("execution_semantics", ExecutionSemantics.AT_LEAST_ONCE)
            if isinstance(raw_semantics, str):
                try:
                    tool_semantics = ExecutionSemantics(raw_semantics)
                except ValueError:
                    tool_semantics = ExecutionSemantics.AT_LEAST_ONCE
            elif isinstance(raw_semantics, ExecutionSemantics):
                tool_semantics = raw_semantics
            else:
                tool_semantics = ExecutionSemantics.AT_LEAST_ONCE

            raw_risk = node.get("risk_level", RiskLevel.LOW)
            if isinstance(raw_risk, str):
                try:
                    risk_level = RiskLevel(raw_risk)
                except ValueError:
                    risk_level = RiskLevel.LOW
            elif isinstance(raw_risk, RiskLevel):
                risk_level = raw_risk
            else:
                risk_level = RiskLevel.LOW

        attempt = 1
        last_err: Exception | None = None

        while attempt <= policy.max_attempts:
            # Validate fencing token before each attempt
            is_valid = await self.coordinator.validate_lease_and_fencing_token(
                execution_id=execution_id,
                worker_id=self.worker.worker_id,
                expected_token=fencing_token,
            )
            if not is_valid:
                from nexusai.brain.domain.execution_coordination import FencingTokenError

                raise FencingTokenError(
                    f"Worker '{self.worker.worker_id}' fencing token {fencing_token} was rejected by store"
                )

            try:
                result = await step_executor(node, attempt)

                # Persist step completion
                tool_res = ToolExecutionResult(
                    request_id=f"step-{node_id}",
                    tool_name=str(node.get("tool", "tool")),
                    success=True,
                    output=result,
                )
                await self.store.save_node_result_atomically(
                    execution_id=execution_id,
                    node_id=node_id,
                    status=NodeExecutionStatus.COMPLETED,
                    result=tool_res,
                )

                if self.audit_store:
                    try:
                        audit_ev = AuditEvent(
                            event_id=f"audit-step-{execution_id}-{node_id}-{time.time_ns()}",
                            event_type="TOOL_EXECUTION_COMPLETED",
                            session_id="session-durable",
                            execution_id=execution_id,
                            plan_fingerprint="fp-durable",
                            sequence_number=0,
                            timestamp=time.time(),
                            node_id=node_id,
                            tool_id=str(node.get("tool", "tool")),
                            worker_id=self.worker.worker_id,
                            actor=actor,
                            outcome="SUCCESS",
                            severity="INFO",
                            fencing_token=fencing_token,
                            metadata={
                                "execution_semantics": tool_semantics.value,
                                "attempt": attempt,
                            },
                        )
                        await self.audit_store.append_event(audit_ev)
                    except Exception as a_err:
                        logger.debug("Failed to append step audit event: {}", a_err)

                return result

            except Exception as err:
                last_err = err
                logger.warning(
                    "Step {} of execution {} failed on attempt {}/{}: {}",
                    node_id,
                    execution_id,
                    attempt,
                    policy.max_attempts,
                    err,
                )

                # Check if retryable per policy
                if not policy.is_retryable(err) or attempt >= policy.max_attempts:
                    fail_res = ToolExecutionResult(
                        request_id=f"step-{node_id}",
                        tool_name=str(node.get("tool", "tool")),
                        success=False,
                        error_message=str(err),
                    )
                    await self.store.save_node_result_atomically(
                        execution_id=execution_id,
                        node_id=node_id,
                        status=NodeExecutionStatus.FAILED,
                        result=fail_res,
                    )
                    raise

                # Check side-effect semantics before retry
                if tool_semantics == ExecutionSemantics.AT_LEAST_ONCE:
                    logger.warning(
                        "Tool '{}' has AT_LEAST_ONCE semantics; retry may cause duplicate side effects",
                        node.get("tool"),
                    )
                    if risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL):
                        approval_granted = node.get("retry_approval_granted", False)
                        if not approval_granted:
                            raise ApprovalRequiredError(
                                f"Retry for tool '{node.get('tool')}' (risk: {risk_level.value}) requires explicit human approval."
                            )

                delay = policy.calculate_delay(attempt)
                logger.info(
                    "Retrying step {} (semantics: {}) in {:.2f}s...",
                    node_id,
                    tool_semantics.value,
                    delay,
                )
                await asyncio.sleep(delay)
                attempt += 1

        if last_err:
            raise last_err
        raise RuntimeError(f"Step {node_id} exceeded maximum retry attempts")

    async def resume_execution(
        self,
        execution_id: str,
        nodes: list[dict[str, Any]],
        step_executor: Callable[[dict[str, Any], int], Coroutine[Any, Any, Any]],
        actor: str = "recovery-worker",
    ) -> dict[str, Any]:
        """Resume an interrupted or crashed execution from the last durable checkpoint."""
        record = await self.store.load_execution(execution_id)
        if record is None:
            raise ValueError(f"Execution '{execution_id}' does not exist in store")

        if (
            record.status == ExecutionStatus.CANCELLED
            or await self.store.is_cancellation_requested(execution_id)
        ):
            logger.info("Cannot resume cancelled execution {}", execution_id)
            return {
                "status": DurableExecutionState.CANCELLED.value,
                "execution_id": execution_id,
                "resumed": False,
            }

        logger.info("Resuming durable execution {} from checkpoints", execution_id)
        return await self.execute_dag(
            execution_id=execution_id,
            plan_id=record.plan_id,
            nodes=nodes,
            step_executor=step_executor,
            actor=actor,
            tenant_id=record.tenant_id,
        )

    async def cancel_execution(self, execution_id: str, reason: str = "") -> bool:
        """Durably cancel an execution, signaling in-memory tasks and preventing recovery."""
        await self.store.mark_cancellation_requested(execution_id)

        # Cancel running in-memory task if active
        if execution_id in self._active_tasks:
            task = self._active_tasks[execution_id]
            if not task.done():
                task.cancel()

        # Update durable state
        current_lease = await self.coordinator.get_current_lease(execution_id)
        token = current_lease.fencing_token if current_lease else 1
        try:
            await self._transition_state(
                execution_id=execution_id,
                to_state=DurableExecutionState.CANCELLED,
                fencing_token=token,
                actor="user",
                reason=reason or "Explicit user cancellation request",
            )
        except InvalidStateTransitionError:
            pass  # If already terminal or cancelled

        logger.info("Execution {} marked CANCELLED durably", execution_id)
        return True
