"""
Enforced SLA Latency Regression Benchmark Test Suite for Memory Engine operations.
"""

import time
import pytest

from nexusai.memory.bootstrap import MemoryEngineBootstrap
from nexusai.memory.config import MemoryEngineConfig
from nexusai.memory.metrics import MemoryMetricsCollector
from nexusai.memory.storage import InMemoryMemoryStore
from nexusai.memory.vector import InMemoryVectorStore, VectorRecord


@pytest.mark.asyncio
async def test_sla_latency_regression_benchmarks():
    """Verify operation P95 latencies stay strictly below SLA regression threshold bounds."""
    config = MemoryEngineConfig(vector_provider="in_memory", embedding_provider="mock")
    service = MemoryEngineBootstrap.create_service(config)
    await service.initialize()
    await service.start()

    metrics = MemoryMetricsCollector()

    # 1. Measure Store Latencies (50 samples)
    for i in range(50):
        t0 = time.time()
        await service.store(raw_text=f"SLA benchmark store content {i}")
        metrics.record_latency("store_op", (time.time() - t0) * 1000.0)

    # 2. Measure Search Latencies (50 samples)
    for i in range(50):
        t0 = time.time()
        await service.search(query=f"SLA benchmark query {i}", top_k=5)
        metrics.record_latency("search_op", (time.time() - t0) * 1000.0)

    # 3. Measure Vector Store Upsert Latencies (50 samples)
    vector_store = InMemoryVectorStore(dimensions=8)
    for i in range(50):
        v_rec = VectorRecord(record_id=f"v_sla_{i}", vector=[0.1] * 8, namespace="default")
        t0 = time.time()
        await vector_store.upsert(v_rec)
        metrics.record_latency("vector_op", (time.time() - t0) * 1000.0)

    # 4. Enforce SLA Bounds Assertions
    store_p95 = metrics.get_percentiles("store_op")["p95"]
    search_p95 = metrics.get_percentiles("search_op")["p95"]
    vector_p95 = metrics.get_percentiles("vector_op")["p95"]

    assert store_p95 < 15.0, f"Store P95 latency SLA breached: {store_p95:.2f}ms >= 15.0ms"
    assert search_p95 < 80.0, f"Search P95 latency SLA breached: {search_p95:.2f}ms >= 80.0ms"
    assert vector_p95 < 40.0, f"Vector P95 latency SLA breached: {vector_p95:.2f}ms >= 40.0ms"

    await service.shutdown()
