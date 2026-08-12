"""Postgres persistence adapters contract conformance integration test suite."""

from __future__ import annotations

import asyncio
import pytest

from nexusai.infrastructure.persistence.postgres_approval_store import PostgresApprovalStore
from nexusai.infrastructure.persistence.postgres_audit_store import PostgresAuditStore
from tests.contracts.test_approval_store_contract import verify_approval_store_contract
from tests.contracts.test_audit_store_contract import verify_audit_store_contract


@pytest.mark.asyncio
async def test_postgres_persistence_adapters_conformance() -> None:
    """Verify PostgresApprovalStore and PostgresAuditStore satisfy domain contract specifications."""
    app_store = PostgresApprovalStore()
    await verify_approval_store_contract(app_store)

    audit_store = PostgresAuditStore()
    await verify_audit_store_contract(audit_store)


if __name__ == "__main__":
    asyncio.run(test_postgres_persistence_adapters_conformance())
    print("ALL POSTGRES PERSISTENCE CONFORMANCE TESTS PASSED SUCCESSFULLY!")
