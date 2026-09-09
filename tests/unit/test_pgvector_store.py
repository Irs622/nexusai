"""Unit tests for PgVectorStore PostgreSQL vector database adapter."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from nexusai.memory.contracts.vector import (
    DistanceMetric,
    VectorCapabilities,
    VectorRecord,
)
from nexusai.memory.vector.compliance import VectorComplianceSuite
from nexusai.memory.vector.pgvector import PgVectorStore


@pytest.mark.asyncio
async def test_pgvector_store_fallback_compliance() -> None:
    """Verify PgVectorStore operates in fallback mode when unconfigured and passes VectorComplianceSuite."""
    store = PgVectorStore(dimensions=4, fallback_enabled=True)
    assert store.capabilities.dimensions == 4
    assert DistanceMetric.COSINE in store.capabilities.supported_metrics

    # Must pass all behavioral requirements of VectorComplianceSuite
    await VectorComplianceSuite.verify_vector_store_compliance(store)
    assert store.is_fallback is True

    health = await store.health()
    assert health["healthy"] is True
    assert health["is_fallback"] is True


@pytest.mark.asyncio
async def test_pgvector_store_mock_pool_execution() -> None:
    """Verify PgVectorStore SQL generation, schema bootstrapping, and queries using mock asyncpg connection pool."""
    mock_conn = AsyncMock()
    mock_conn.execute = AsyncMock(return_value="DELETE 1")
    mock_conn.executemany = AsyncMock()
    mock_conn.fetchval = AsyncMock(return_value=5)

    # Sample returned row for get() and search()
    fake_row = {
        "record_id": "v_test_1",
        "namespace": "agent_mem",
        "vector": "[0.10000000, 0.20000000, 0.30000000, 0.40000000]",
        "metadata": json.dumps({"topic": "science"}),
        "payload": "Sample payload text",
        "distance": 0.05,
        "similarity": 0.95,
    }
    mock_conn.fetchrow = AsyncMock(return_value=fake_row)
    mock_conn.fetch = AsyncMock(return_value=[fake_row])

    mock_pool = MagicMock()
    mock_ctx = AsyncMock()
    mock_ctx.__aenter__.return_value = mock_conn
    mock_ctx.__aexit__.return_value = None
    mock_pool.acquire.return_value = mock_ctx
    mock_pool.close = AsyncMock()

    store = PgVectorStore(
        table_name="custom_vectors",
        dimensions=4,
        index_type="hnsw",
        pool=mock_pool,
        fallback_enabled=False,
    )

    # 1. Upsert
    rec = VectorRecord(
        record_id="v_test_1",
        vector=[0.1, 0.2, 0.3, 0.4],
        metadata={"topic": "science"},
        namespace="agent_mem",
        payload="Sample payload text",
    )
    await store.upsert(rec)
    assert mock_conn.execute.called

    # Verify schema bootstrap was called
    executed_queries = [call.args[0] for call in mock_conn.execute.call_args_list]
    assert any("CREATE EXTENSION IF NOT EXISTS vector" in q for q in executed_queries)
    assert any("CREATE TABLE IF NOT EXISTS custom_vectors" in q for q in executed_queries)
    assert any("USING hnsw" in q for q in executed_queries)

    # 2. Get
    fetched = await store.get("v_test_1", namespace="agent_mem")
    assert fetched is not None
    assert fetched.record_id == "v_test_1"
    assert fetched.vector == [0.1, 0.2, 0.3, 0.4]
    assert fetched.metadata == {"topic": "science"}

    # 3. Search with metadata filtering
    matches = await store.search(
        query_vector=[0.1, 0.2, 0.3, 0.4],
        top_k=3,
        namespace="agent_mem",
        filter_dict={"topic": "science"},
    )
    assert len(matches) == 1
    assert matches[0].record_id == "v_test_1"
    assert matches[0].similarity == 0.95
    assert matches[0].distance == 0.05

    # 4. Batch Upsert
    await store.batch_upsert([rec, rec])
    assert mock_conn.executemany.called

    # 5. Delete & Batch Delete
    deleted = await store.delete("v_test_1", namespace="agent_mem")
    assert deleted is True

    mock_conn.execute.return_value = "DELETE 2"
    batch_del = await store.batch_delete(["v_test_1", "v_test_2"], namespace="agent_mem")
    assert batch_del == 2

    # 6. Count and Clear
    count_val = await store.count(namespace="agent_mem")
    assert count_val == 5

    await store.clear(namespace="agent_mem")
    assert any(
        "DELETE FROM custom_vectors WHERE namespace = $1" in call.args[0]
        for call in mock_conn.execute.call_args_list
    )

    # 7. Health & Close
    health = await store.health()
    assert health["healthy"] is True
    assert health["table"] == "custom_vectors"
    assert health["index_type"] == "hnsw"

    await store.close()
    assert mock_pool.close.called


def test_pgvector_capabilities_descriptor() -> None:
    """Verify capabilities descriptor properties."""
    store = PgVectorStore(dimensions=1536)
    caps: VectorCapabilities = store.capabilities
    assert caps.provider_name == "pgvector_store"
    assert caps.dimensions == 1536
    assert caps.supports_namespaces is True
    assert caps.supports_metadata_filtering is True
    assert caps.supports_batch is True
