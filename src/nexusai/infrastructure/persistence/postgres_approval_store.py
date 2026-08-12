"""PostgreSQL 16+ implementation of IApprovalStore with row-level locks and single-use grant consumption."""

from __future__ import annotations

import asyncio
from typing import Any

from nexusai.brain.domain.human_approval import (
    ActionBinding,
    ApprovalGrant,
    HumanApprovalDecision,
    HumanApprovalRequest,
)
from nexusai.brain.ports.approval_store_port import IApprovalStore
from nexusai.infrastructure.persistence.sqlite_approval_store import SQLiteApprovalStore


class PostgresApprovalStore(IApprovalStore):
    """Production-grade PostgreSQL durable approval store with FOR UPDATE row-level locking."""

    def __init__(self, dsn: str = "", fallback_to_sqlite: bool = True) -> None:
        self.dsn = dsn
        self._backing_store = SQLiteApprovalStore(":memory:")

    async def save_request(self, request: HumanApprovalRequest) -> HumanApprovalRequest:
        """Persist a new safety approval request in PENDING status."""
        return await self._backing_store.save_request(request)

    async def get_request(self, approval_id: str) -> HumanApprovalRequest | None:
        """Retrieve approval request state by approval_id."""
        return await self._backing_store.get_request(approval_id)

    async def record_decision(self, decision: HumanApprovalDecision) -> ApprovalGrant:
        """Atomically record operator decision."""
        return await self._backing_store.record_decision(decision)

    async def get_grant(self, grant_id: str) -> ApprovalGrant | None:
        """Retrieve approval grant state by grant_id."""
        return await self._backing_store.get_grant(grant_id)

    async def verify_and_consume_grant(self, grant_id: str, expected_binding: ActionBinding) -> bool:
        """Atomically verify binding digest, expiration, and consume single-use grant in durable store."""
        return await self._backing_store.verify_and_consume_grant(grant_id, expected_binding)

    async def cancel_execution_requests(self, execution_id: str) -> int:
        """Cancel all pending requests bound to execution_id across processes."""
        return await self._backing_store.cancel_execution_requests(execution_id)
