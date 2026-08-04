"""
NexusAI Memory Engine public API re-exports.
"""

from __future__ import annotations

from nexusai.memory.bootstrap import MemoryEngineBootstrap
from nexusai.memory.config import MemoryEngineConfig
from nexusai.memory.contracts import (
    DistanceMetric,
    EmbeddingCapabilities,
    EmbeddingProvider,
    MemoryStorage,
    PipelineTrace,
    QueryResult,
    RetrievalContext,
    RetrievalStage,
    StageTrace,
    VectorCapabilities,
    VectorMatch,
    VectorRecord,
    VectorStore,
)
from nexusai.memory.domain import (
    MemoryContent,
    MemoryMetadata,
    MemoryRecord,
    MemoryScope,
    MemoryType,
)
from nexusai.memory.embedding import (
    EmbeddingComplianceSuite,
    LocalEmbeddingProvider,
    MockEmbeddingProvider,
    RemoteEmbeddingProvider,
)
from nexusai.memory.exceptions import (
    EmbeddingError,
    MemoryError,
    MemoryStorageError,
    MemoryTransactionError,
    RetrievalError,
    VectorStoreError,
)
from nexusai.memory.metrics import MemoryMetricsCollector
from nexusai.memory.pipeline import (
    ClaudePromptFormatter,
    ContextBuilder,
    GeminiPromptFormatter,
    JSONPromptFormatter,
    MarkdownPromptFormatter,
    OpenAIPromptFormatter,
    PipelineBuilder,
    PipelineFactory,
    PromptFormatter,
    RetrievalPipeline,
    RetrievalPipelineConfig,
    StructuredContext,
    StructuredContextItem,
    XMLPromptFormatter,
)
from nexusai.memory.policies import (
    DeduplicationPolicy,
    MemoryPolicy,
    PolicyContext,
    PolicyEngine,
    RetentionPolicy,
)
from nexusai.memory.repository import (
    MemoryRecordRepository,
    VectorRepository,
)
from nexusai.memory.serializer import (
    JSONMemorySerializer,
    MemorySerializer,
)
from nexusai.memory.service import MemoryService
from nexusai.memory.services import (
    MemoryAdminService,
    MemoryCommandService,
    MemoryQueryService,
)
from nexusai.memory.stages import (
    ImportanceStage,
    MetadataFilterStage,
    RankingStage,
    RecencyBoostStage,
    SimilarityStage,
    WeightedScoringStage,
)
from nexusai.memory.storage import (
    FileMemoryStore,
    InMemoryMemoryStore,
    SQLiteMemoryStore,
    StorageComplianceSuite,
)
from nexusai.memory.uow import MemoryUnitOfWork
from nexusai.memory.usecases import (
    ForgetMemoryUseCase,
    RetrieveMemoryUseCase,
    SearchMemoryUseCase,
    StoreMemoryUseCase,
)
from nexusai.memory.vector import (
    ChromaVectorStore,
    InMemoryVectorStore,
    MockVectorStore,
    VectorComplianceSuite,
)

__all__ = [
    "ChromaVectorStore",
    "ClaudePromptFormatter",
    "ContextBuilder",
    "DeduplicationPolicy",
    "DistanceMetric",
    "EmbeddingCapabilities",
    "EmbeddingComplianceSuite",
    "EmbeddingError",
    "EmbeddingProvider",
    "FileMemoryStore",
    "ForgetMemoryUseCase",
    "GeminiPromptFormatter",
    "ImportanceStage",
    "InMemoryMemoryStore",
    "InMemoryVectorStore",
    "JSONMemorySerializer",
    "JSONPromptFormatter",
    "LocalEmbeddingProvider",
    "MarkdownPromptFormatter",
    "MemoryAdminService",
    "MemoryCommandService",
    "MemoryContent",
    "MemoryEngineBootstrap",
    "MemoryEngineConfig",
    "MemoryError",
    "MemoryMetadata",
    "MemoryMetricsCollector",
    "MemoryPolicy",
    "MemoryQueryService",
    "MemoryRecord",
    "MemoryRecordRepository",
    "MemoryScope",
    "MemoryService",
    "MemoryStorage",
    "MemoryStorageError",
    "MemoryTransactionError",
    "MemoryType",
    "MemoryUnitOfWork",
    "MetadataFilterStage",
    "MockEmbeddingProvider",
    "MockVectorStore",
    "OpenAIPromptFormatter",
    "PipelineBuilder",
    "PipelineFactory",
    "PipelineTrace",
    "PolicyContext",
    "PolicyEngine",
    "PromptFormatter",
    "QueryResult",
    "RankingStage",
    "RecencyBoostStage",
    "RemoteEmbeddingProvider",
    "RetentionPolicy",
    "RetrievalContext",
    "RetrievalError",
    "RetrievalPipeline",
    "RetrievalPipelineConfig",
    "RetrievalStage",
    "RetrieveMemoryUseCase",
    "SQLiteMemoryStore",
    "SearchMemoryUseCase",
    "SimilarityStage",
    "StageTrace",
    "StorageComplianceSuite",
    "StoreMemoryUseCase",
    "StructuredContext",
    "StructuredContextItem",
    "VectorCapabilities",
    "VectorComplianceSuite",
    "VectorMatch",
    "VectorRecord",
    "VectorRepository",
    "VectorStore",
    "VectorStoreError",
    "WeightedScoringStage",
    "XMLPromptFormatter",
]
