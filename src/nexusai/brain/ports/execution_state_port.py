"""IExecutionStateStore port contract for durable execution checkpointing and recovery decisions."""

from __future__ import annotations

from typing import Any, Protocol

from nexusai.brain.domain.execution_state import (
    ExecutionRecord,
    ExecutionStatus,
    NodeExecutionStatus,
)
from nexusai.brain.domain.recovery import RecoveryDecision
from nexusai.brain.ports.tool_port import ToolExecutionResult


class IExecutionStateStore(Protocol):
    """Abstract port decoupling Brain Runtime engine from durable persistence implementations."""

    async def create_execution(self, record: ExecutionRecord) -> None:
        """Persist a new execution record and initialize node checkpoints."""
        ...

    async def load_execution(self, execution_id: str) -> ExecutionRecord | None:
        """Load an execution record and its node checkpoints from durable storage."""
        ...

    async def mark_node_running(self, execution_id: str, node_id: Any) -> None:
        """Checkpoint node transition to RUNNING state."""
        ...

    async def save_node_result_atomically(
        self,
        execution_id: str,
        node_id: Any,
        status: NodeExecutionStatus,
        result: ToolExecutionResult,
    ) -> None:
        """Atomically persist tool execution output and terminal node status in a single transaction."""
        ...

    async def save_recovery_decision_atomically(
        self,
        execution_id: str,
        node_id: Any,
        status: NodeExecutionStatus,
        decision: RecoveryDecision,
    ) -> None:
        """Atomically persist recovery policy decision, idempotency key, failure class, and next_retry_at timestamp."""
        ...

    async def mark_node_cancelled(self, execution_id: str, node_id: Any) -> None:
        """Checkpoint node transition to CANCELLED state."""
        ...

    async def update_execution_status(
        self,
        execution_id: str,
        status: ExecutionStatus,
    ) -> None:
        """Update overall execution status."""
        ...
