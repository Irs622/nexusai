"""IReconciliationPort protocol contract for side-effect reconciliation."""

from __future__ import annotations

from typing import Any, Protocol

from nexusai.brain.ports.tool_port import ToolExecutionResult


class IReconciliationPort(Protocol):
    """Abstract port interface for reconciling uncertain side-effecting operations."""

    async def reconcile(
        self,
        execution_id: str,
        node_id: Any,
        idempotency_key: str | None = None,
    ) -> ToolExecutionResult | None:
        """Attempt to query external system or local log to verify whether side-effect completed.

        Returns:
            ToolExecutionResult with success=True if side-effect completed externally,
            ToolExecutionResult with success=False if side-effect failed externally,
            None if status remains UNKNOWN / reconciliation cannot determine outcome.
        """
        ...


class DefaultReconciliationAdapter(IReconciliationPort):
    """Default fallback reconciler for offline mode and deterministic testing."""

    def __init__(self, deterministic_outcomes: dict[str, ToolExecutionResult | None] | None = None) -> None:
        self.outcomes = deterministic_outcomes or {}

    async def reconcile(
        self,
        execution_id: str,
        node_id: Any,
        idempotency_key: str | None = None,
    ) -> ToolExecutionResult | None:
        key = idempotency_key or f"{execution_id}:{node_id}"
        return self.outcomes.get(key, None)
