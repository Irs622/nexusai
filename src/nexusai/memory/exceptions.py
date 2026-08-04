"""
Hierarchical Memory Error classes inheriting from NexusAIError.
"""

from __future__ import annotations

from nexusai.core.errors import NexusAIError


class MemoryError(NexusAIError):
    """Base exception class for all Memory Engine errors."""

    pass


class MemoryStorageError(MemoryError):
    """Raised when a storage engine operation fails."""

    pass


class EmbeddingError(MemoryError):
    """Raised when an embedding provider fails to generate vector representations."""

    pass


class VectorStoreError(MemoryError):
    """Raised when a vector database operation or similarity search fails."""

    pass


class RetrievalError(MemoryError):
    """Raised when a retrieval pipeline stage fails."""

    pass


class MemoryTransactionError(MemoryError):
    """Raised when a memory unit of work transaction fails or rolls back."""

    pass
