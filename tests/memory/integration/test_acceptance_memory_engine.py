"""
Public API Acceptance Test Suite for NexusAI Memory Engine.
"""

import pytest

from nexusai.memory.bootstrap import MemoryEngineBootstrap
from nexusai.memory.config import MemoryEngineConfig
from nexusai.memory.domain.record import MemoryScope, MemoryType


@pytest.mark.asyncio
async def test_memory_engine_public_api_acceptance():
    """Acceptance test running full memory lifecycle exclusively via MemoryService public API facade."""
    config = MemoryEngineConfig(
        storage_dir=".nexusai/test_acceptance_storage",
        vector_provider="in_memory",
        embedding_provider="mock",
    )
    service = MemoryEngineBootstrap.create_service(config)

    await service.initialize()
    await service.start()

    # 1. Health Probe
    health = await service.health()
    assert health["status"] == "healthy"
    assert health["storage"] == "healthy"

    # 2. Store Record via Public API
    record = await service.store(
        raw_text="Acceptance test memory content",
        memory_type=MemoryType.EPISODIC,
        scope=MemoryScope.USER,
    )
    assert record.id != ""
    assert record.content.raw_text == "Acceptance test memory content"

    # 3. Retrieve Record via Public API
    fetched = await service.retrieve(record.id)
    assert fetched is not None
    assert fetched.id == record.id

    # 4. Search Memory via Public API
    search_res = await service.search(query="Acceptance test", top_k=5)
    assert search_res is not None

    # 5. Archive Record via Public API
    archived_success = await service.archive(record.id, reason="acceptance_test")
    assert archived_success is True

    # 6. Forget Record via Public API
    forgotten = await service.forget(record.id)
    assert forgotten is True

    # 7. Operational Metrics
    metrics_summary = service.metrics()
    assert metrics_summary["counters"]["store_count"] >= 1

    # 8. Graceful Shutdown
    await service.shutdown()
