"""
Memory contracts package re-exports.
"""

from __future__ import annotations

from nexusai.memory.contracts.content import MemoryContent
from nexusai.memory.contracts.embedding import EmbeddingCapabilities, EmbeddingProvider
from nexusai.memory.contracts.metadata import MemoryMetadata
from nexusai.memory.contracts.record import MemoryRecord, MemoryScope, MemoryType
from nexusai.memory.contracts.retrieval import QueryResult, RetrievalContext, RetrievalStage
from nexusai.memory.contracts.storage import MemoryStorage
from nexusai.memory.contracts.vector import VectorMatch, VectorStore

__all__ = [
    "EmbeddingCapabilities",
    "EmbeddingProvider",
    "MemoryContent",
    "MemoryMetadata",
    "MemoryRecord",
    "MemoryScope",
    "MemoryStorage",
    "MemoryType",
    "QueryResult",
    "RetrievalContext",
    "RetrievalStage",
    "VectorMatch",
    "VectorStore",
]
