from __future__ import annotations
"""
Unit tests for Milestone 2.4.2: MemoryUnitOfWork, Domain Invariants, Outbox, and MemoryService.
"""

from typing import Sequence
import pytest

from nexusai.kernel.outbox import JSONOutboxSerializer, OutboxRecord, OutboxRepository, OutboxStatus
from nexusai.kernel.service import ServiceDescriptor, ServiceLifecycleState
from nexusai.kernel.transaction import AsyncTransaction
from nexusai.memory.contracts.embedding import EmbeddingCapabilities, EmbeddingProvider
from nexusai.memory.contracts.retrieval import RetrievalContext, RetrievalStage
from nexusai.memory.contracts.vector import VectorMatch
from nexusai.memory.domain import MemoryContent, MemoryMetadata, MemoryRecord, MemoryScope, MemoryType
from nexusai.memory.pipeline import PipelineBuilder, RetrievalPipelineConfig
from nexusai.memory.repository import MemoryRecordRepository, VectorRepository
from nexusai.memory.service import MemoryService
from nexusai.memory.uow import MemoryUnitOfWork


class MockAsyncTransaction(AsyncTransaction):
    async def begin(self) -> None:
        pass

    async def commit(self) -> None:
        pass

    async def rollback(self) -> None:
        pass


class MockRecordRepository(MemoryRecordRepository):
    def __init__(self) -> None:
        self.store: dict[str, MemoryRecord] = {}

    async def add(self, record: MemoryRecord) -> None:
        self.store[record.id] = record

    async def get_by_id(self, record_id: str) -> MemoryRecord | None:
        return self.store.get(record_id)

    async def delete(self, record_id: str) -> bool:
        if record_id in self.store:
            del self.store[record_id]
            return True
        return False

    async def list_all(self, limit: int = 100) -> Sequence[MemoryRecord]:
        return list(self.store.values())[:limit]


class MockVectorRepository(VectorRepository):
    def __init__(self) -> None:
        self.vectors: dict[str, Sequence[float]] = {}

    async def upsert_vector(self, embedding_id: str, vector: Sequence[float], metadata: dict[str, str] | None = None) -> None:
        self.vectors[embedding_id] = vector

    async def delete_vector(self, embedding_id: str) -> bool:
        if embedding_id in self.vectors:
            del self.vectors[embedding_id]
            return True
        return False

    async def search(self, query_vector: Sequence[float], top_k: int = 5) -> Sequence[VectorMatch]:
        results = []
        for eid in list(self.vectors.keys())[:top_k]:
            results.append(VectorMatch(embedding_id=eid, score=0.9, metadata={}))
        return results


class MockOutboxRepository(OutboxRepository):
    def __init__(self) -> None:
        self.records: list[OutboxRecord] = []

    async def enqueue(self, record: OutboxRecord) -> None:
        self.records.append(record)

    async def fetch_pending(self, limit: int = 100) -> Sequence[OutboxRecord]:
        return [r for r in self.records if r.status == OutboxStatus.PENDING][:limit]

    async def mark_dispatched(self, record_id: str) -> None:
        for r in self.records:
            if r.id == record_id:
                r.status = OutboxStatus.DISPATCHED

    async def mark_failed(self, record_id: str, error: str) -> None:
        for r in self.records:
            if r.id == record_id:
                r.status = OutboxStatus.FAILED
                r.error_message = error


class MockMemoryUnitOfWork(MemoryUnitOfWork):
    def __init__(self) -> None:
        self._records = MockRecordRepository()
        self._vector = MockVectorRepository()
        self._outbox = MockOutboxRepository()

    @property
    def records(self) -> MemoryRecordRepository:
        return self._records

    @property
    def vector(self) -> VectorRepository:
        return self._vector

    @property
    def outbox(self) -> OutboxRepository:
        return self._outbox

    def transaction(self) -> AsyncTransaction:
        return MockAsyncTransaction()


class MockEmbeddingProvider(EmbeddingProvider):
    @property
    def capabilities(self) -> EmbeddingCapabilities:
        return EmbeddingCapabilities(
            model_name="mock-embedder",
            max_dimension=3,
        )

    async def embed_text(self, text: str) -> list[float]:
        return [0.1, 0.2, 0.3]

    async def embed_batch(self, texts: Sequence[str]) -> list[list[float]]:
        return [[0.1, 0.2, 0.3] for _ in texts]


class MockStage(RetrievalStage):
    async def execute(self, context: RetrievalContext) -> None:
        context.scores = {r.id: 0.95 for r in context.candidate_records}


def test_domain_aggregate_invariants():
    content = MemoryContent(raw_text="Test memory content")
    record = MemoryRecord(content=content)

    record.touch()
    assert record.metadata.updated_at > 0

    record.archive()
    assert record.metadata.archived is True

    record.attach_embedding(embedding_id="vec_123")
    assert record.content.embedding_id == "vec_123"

    record.update_summary(summary="Short summary")
    assert record.content.summary == "Short summary"

    record.record_domain_event({"type": "MemoryStored"})
    events = record.pull_events()
    assert len(events) == 1
    assert len(record.pull_events()) == 0


def test_json_outbox_serializer():
    serializer = JSONOutboxSerializer()
    payload = serializer.serialize({"event_id": "ev_1", "type": "MemoryStored"})
    deserialized = serializer.deserialize(payload)
    assert deserialized["payload"]["event_id"] == "ev_1"


@pytest.mark.asyncio
async def test_memory_service_full_flow():
    from nexusai.memory.bootstrap import MemoryEngineBootstrap
    service = MemoryEngineBootstrap.create_service()

    await service.start()
    assert service.state == ServiceLifecycleState.RUNNING

    record = await service.store(raw_text="NexusAI Plugin System")
    assert record.content.raw_text == "NexusAI Plugin System"

    fetched = await service.retrieve(record.id)
    assert fetched is not None
    assert fetched.id == record.id

    query_res = await service.search(query="Plugin")
    assert len(query_res.records) >= 1

    deleted = await service.forget(record.id)
    assert deleted is True
    assert await service.retrieve(record.id) is None

    health = await service.health()
    assert health["status"] == "healthy"
