"""
Unit tests for Memory contracts, value objects, exceptions, and models.
"""

from nexusai.memory.contracts import (
    EmbeddingCapabilities,
    MemoryContent,
    MemoryRecord,
    MemoryScope,
    MemoryType,
    RetrievalContext,
)
from nexusai.memory.exceptions import MemoryError, MemoryStorageError


def test_memory_record_creation_defaults():
    content = MemoryContent(raw_text="User wants to install plugins.")
    record = MemoryRecord(content=content)

    assert record.memory_type == MemoryType.EPISODIC
    assert record.scope == MemoryScope.SESSION
    assert record.content.raw_text == "User wants to install plugins."
    assert record.schema_version == "1.0.0"


def test_embedding_capabilities_value_object():
    caps = EmbeddingCapabilities(
        model_name="ollama/nomic-embed-text",
        dimensions=768,
        supports_batch=True,
    )
    assert caps.model_name == "ollama/nomic-embed-text"
    assert caps.dimensions == 768
    assert caps.supports_batch is True


def test_retrieval_context_defaults():
    context = RetrievalContext(query="How to run tests?")
    assert context.query == "How to run tests?"
    assert len(context.candidate_records) == 0
    assert len(context.scores) == 0


def test_memory_exception_hierarchy():
    err = MemoryStorageError("SQLite connection failed")
    assert isinstance(err, MemoryError)
    assert str(err) == "SQLite connection failed"
