import pytest
pytestmark = pytest.mark.integration
"""
Provider Replaceability Matrix Test Suite proving provider-agnostic replaceability across storage/vector/embedding combinations.
"""

import pytest

from nexusai.memory.bootstrap import MemoryEngineBootstrap
from nexusai.memory.config import MemoryEngineConfig
from nexusai.memory.domain.record import MemoryScope, MemoryType


@pytest.mark.asyncio
async def test_provider_matrix_1_sqlite_inmemory_mock():
    """Matrix 1: SQLiteMemoryStore + InMemoryVectorStore + MockEmbeddingProvider."""
    config = MemoryEngineConfig(
        storage_dir=".nexusai/test_matrix_1",
        vector_provider="in_memory",
        embedding_provider="mock",
    )
    service = MemoryEngineBootstrap.create_service(config)
    await service.initialize()
    await service.start()

    record = await service.store("Matrix 1 test content", memory_type=MemoryType.EPISODIC)
    assert record.id != ""

    fetched = await service.retrieve(record.id)
    assert fetched is not None
    assert fetched.content.raw_text == "Matrix 1 test content"

    await service.shutdown()


@pytest.mark.asyncio
async def test_provider_matrix_2_file_chroma_local():
    """Matrix 2: FileMemoryStore / SQLite + ChromaVectorStore + LocalEmbeddingProvider."""
    config = MemoryEngineConfig(
        storage_dir=".nexusai/test_matrix_2",
        vector_provider="chroma",
        embedding_provider="local",
    )
    service = MemoryEngineBootstrap.create_service(config)
    await service.initialize()
    await service.start()

    record = await service.store("Matrix 2 test content", memory_type=MemoryType.SEMANTIC)
    assert record.id != ""

    fetched = await service.retrieve(record.id)
    assert fetched is not None
    assert fetched.content.raw_text == "Matrix 2 test content"

    await service.shutdown()


@pytest.mark.asyncio
async def test_provider_matrix_3_inmemory_mockvector_remote():
    """Matrix 3: InMemoryMemoryStore + MockVectorStore + RemoteEmbeddingProvider."""
    config = MemoryEngineConfig(
        storage_dir=":memory:",
        vector_provider="mock",
        embedding_provider="remote",
    )
    service = MemoryEngineBootstrap.create_service(config)
    await service.initialize()
    await service.start()

    record = await service.store("Matrix 3 test content", memory_type=MemoryType.PROCEDURAL)
    assert record.id != ""

    fetched = await service.retrieve(record.id)
    assert fetched is not None
    assert fetched.content.raw_text == "Matrix 3 test content"

    await service.shutdown()
