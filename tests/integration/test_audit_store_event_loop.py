"""Regression test: SQLiteAuditStore writes must not stall the asyncio event loop (AUDIT-11)."""

from __future__ import annotations

from pathlib import Path

import pytest

from benchmarks.audit_store_loop_lag import measure_loop_lag
from nexusai.infrastructure.persistence.sqlite_audit_store import SQLiteAuditStore


@pytest.mark.asyncio
async def test_concurrent_audit_writes_keep_event_loop_responsive(tmp_path: Path) -> None:
    store = SQLiteAuditStore(db_path=str(tmp_path / "audit.db"))

    result = await measure_loop_lag(store, writes=200, concurrency=50)

    # Before offloading to threads the loop froze for ~100ms per burst (p95 ≈ 100ms,
    # only a handful of probe wake-ups). Keep a generous ceiling to stay CI-stable.
    assert result["samples"] >= 20
    assert result["p95_ms"] < 50.0
    events = await store.get_events(execution_id="bench")
    assert len(events) == 200
    assert (await store.verify_chain(tenant_id="default")).valid
