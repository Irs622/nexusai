import pytest
pytestmark = pytest.mark.integration
"""
Resiliency and Degraded Health Failure Mode Acceptance Test Suite.
"""

import pytest

from nexusai.kernel.outbox import OutboxDispatcher, OutboxRecord, OutboxStatus
from nexusai.memory.bootstrap import MemoryEngineBootstrap
from nexusai.memory.config import MemoryEngineConfig


class FailingOutboxRepository:
    """Mock repository throwing persistent exceptions to trigger DLQ routing."""

    def __init__(self):
        self._records = [
            OutboxRecord(id="poison_rec_1", event_type="FailingEvent", payload_bytes=b"{}", retry_count=2)
        ]

    async def fetch_pending(self, limit: int = 20):
        return self._records

    async def mark_published(self, record_id: str):
        pass

    async def mark_failed(self, record_id: str, error_message: str):
        for r in self._records:
            if r.id == record_id:
                r.retry_count += 1
                r.status = OutboxStatus.FAILED


@pytest.mark.asyncio
async def test_resilience_degraded_health_mode():
    """Verify health probe status transitions to degraded when subsystem encounters failures."""
    config = MemoryEngineConfig(vector_provider="in_memory", embedding_provider="mock")
    service = MemoryEngineBootstrap.create_service(config)
    await service.initialize()
    await service.start()

    # 1. Normal state
    health_before = await service.health()
    assert health_before["status"] == "healthy"

    # 2. Mark degraded
    service.set_degraded_status(True)
    health_degraded = await service.health()
    assert health_degraded["status"] == "degraded"
    assert health_degraded["storage"]["driver"] == "SQLiteMemoryStore"

    # 3. Graceful retrieval of non-existent record (no crash)
    non_existent = await service.retrieve("invalid_id_999")
    assert non_existent is None

    # 4. Graceful archive of non-existent record (returns False safely)
    archive_res = await service.archive("invalid_id_999")
    assert archive_res is False

    await service.shutdown()


@pytest.mark.asyncio
async def test_outbox_dlq_resilience_routing():
    """Verify poison outbox events exceeding max retries are routed to Dead Letter Queue."""
    failing_repo = FailingOutboxRepository()

    async def failing_handler(record):
        raise RuntimeError("Simulated event bus handler failure")

    dispatcher = OutboxDispatcher(repository=failing_repo, max_retries=3)
    dispatcher.register_handler(failing_handler)

    # Process pending event (retry count will reach 3 -> DLQ)
    await dispatcher.dispatch_pending()

    assert len(dispatcher.dlq_records) == 1
    assert dispatcher.dlq_records[0].id == "poison_rec_1"
