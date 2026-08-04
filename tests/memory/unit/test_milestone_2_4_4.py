"""
Unit tests for Milestone 2.4.4: Embedding Compliance Suite, Serializer DI, and AST Rules A009-A014.
"""

import pytest

from nexusai.memory.domain import MemoryContent, MemoryRecord
from nexusai.memory.embedding import (
    EmbeddingComplianceSuite,
    LocalEmbeddingProvider,
    MockEmbeddingProvider,
    RemoteEmbeddingProvider,
)
from nexusai.memory.serializer import JSONMemorySerializer


@pytest.mark.asyncio
async def test_mock_embedding_provider_compliance():
    provider = MockEmbeddingProvider()
    await EmbeddingComplianceSuite.verify_provider_compliance(provider)


@pytest.mark.asyncio
async def test_local_embedding_provider_compliance():
    provider = LocalEmbeddingProvider()
    await EmbeddingComplianceSuite.verify_provider_compliance(provider)


@pytest.mark.asyncio
async def test_remote_embedding_provider_compliance():
    provider = RemoteEmbeddingProvider()
    await EmbeddingComplianceSuite.verify_provider_compliance(provider)


def test_json_memory_serializer():
    serializer = JSONMemorySerializer()
    content = MemoryContent(raw_text="Memory Serializer Test Text")
    record = MemoryRecord(id="ser_rec_1", content=content)

    payload_bytes = serializer.serialize(record)
    assert isinstance(payload_bytes, bytes)

    deserialized = serializer.deserialize(payload_bytes)
    assert deserialized.id == "ser_rec_1"
    assert deserialized.content.raw_text == "Memory Serializer Test Text"
