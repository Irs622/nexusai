"""Unit tests for QdrantVectorStore vector database adapter."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from nexusai.memory.contracts.vector import (
    DistanceMetric,
    VectorCapabilities,
    VectorRecord,
)
from nexusai.memory.vector.compliance import VectorComplianceSuite
from nexusai.memory.vector.qdrant import QdrantVectorStore


@pytest.mark.asyncio
async def test_qdrant_store_fallback_compliance() -> None:
    """Verify QdrantVectorStore operates in fallback mode when unconfigured and passes VectorComplianceSuite."""
    store = QdrantVectorStore(dimensions=4, fallback_enabled=True)
    assert store.capabilities.dimensions == 4
    assert DistanceMetric.COSINE in store.capabilities.supported_metrics

    # Must pass all behavioral requirements of VectorComplianceSuite
    await VectorComplianceSuite.verify_vector_store_compliance(store)
    assert store.is_fallback is True

    health = await store.health()
    assert health["healthy"] is True
    assert health["is_fallback"] is True


@pytest.mark.asyncio
async def test_qdrant_store_mock_client_execution() -> None:
    """Verify QdrantVectorStore operations, collection bootstrapping, and UUID mapping using mock client."""
    mock_client = MagicMock()
    mock_client.get_collections = AsyncMock(return_value=MagicMock(collections=[]))
    mock_client.create_collection = AsyncMock()
    mock_client.upsert = AsyncMock()
    mock_client.close = AsyncMock()

    # Mock retrieved point for get()
    fake_point = MagicMock()
    fake_point.id = str(uuid.uuid4())
    fake_point.vector = [0.1, 0.2, 0.3, 0.4]
    fake_point.payload = {
        "_nexus_record_id": "q_rec_1",
        "_nexus_namespace": "default",
        "_nexus_payload": "Sample Qdrant payload",
        "category": "ai",
    }
    mock_client.retrieve = AsyncMock(return_value=[fake_point])

    # Mock search result
    fake_scored = MagicMock()
    fake_scored.id = fake_point.id
    fake_scored.score = 0.92
    fake_scored.payload = fake_point.payload
    mock_client.search = AsyncMock(return_value=[fake_scored])

    # Mock count and delete
    mock_client.count = AsyncMock(return_value=MagicMock(count=7))
    mock_client.delete = AsyncMock()

    store = QdrantVectorStore(
        collection_name="test_collection",
        dimensions=4,
        client=mock_client,
        fallback_enabled=False,
    )

    # 1. Upsert
    rec = VectorRecord(
        record_id="q_rec_1",
        vector=[0.1, 0.2, 0.3, 0.4],
        metadata={"category": "ai"},
        namespace="default",
        payload="Sample Qdrant payload",
    )
    await store.upsert(rec)
    assert mock_client.upsert.called

    # 2. Get
    fetched = await store.get("q_rec_1", namespace="default")
    assert fetched is not None
    assert fetched.record_id == "q_rec_1"
    assert fetched.vector == [0.1, 0.2, 0.3, 0.4]
    assert fetched.metadata == {"category": "ai"}

    # 3. Search with metadata filtering
    matches = await store.search(
        query_vector=[0.1, 0.2, 0.3, 0.4],
        top_k=2,
        namespace="default",
        filter_dict={"category": "ai"},
    )
    assert len(matches) == 1
    assert matches[0].record_id == "q_rec_1"
    assert matches[0].similarity == 0.92
    assert matches[0].distance == pytest.approx(0.08)

    # 4. Batch Upsert
    await store.batch_upsert([rec, rec])
    assert mock_client.upsert.called

    # 5. Delete & Batch Delete
    del_ok = await store.delete("q_rec_1", namespace="default")
    assert del_ok is True

    del_count = await store.batch_delete(["q_rec_1"], namespace="default")
    assert del_count == 1

    # 6. Count and Clear
    cnt = await store.count(namespace="default")
    assert cnt == 7

    await store.clear(namespace="default")
    assert mock_client.delete.called

    # 7. Health & Close
    health = await store.health()
    assert health["healthy"] is True
    assert health["collection"] == "test_collection"

    await store.close()
    assert mock_client.close.called


def test_qdrant_deterministic_uuid_mapping() -> None:
    """Verify deterministic UUIDv5 generation from arbitrary record IDs."""
    store = QdrantVectorStore(dimensions=128)
    u1 = store._to_uuid("item_42", "default")
    u2 = store._to_uuid("item_42", "default")
    u3 = store._to_uuid("item_42", "other_ns")

    # Consistent for same id and namespace
    assert u1 == u2
    # Namespace isolated
    assert u1 != u3
    # Valid UUID format
    assert uuid.UUID(u1).version == 5


def test_qdrant_capabilities_descriptor() -> None:
    """Verify capabilities descriptor properties."""
    store = QdrantVectorStore(dimensions=768)
    caps: VectorCapabilities = store.capabilities
    assert caps.provider_name == "qdrant_vector_store"
    assert caps.dimensions == 768
    assert caps.supports_namespaces is True
    assert caps.supports_metadata_filtering is True
    assert caps.supports_batch is True
