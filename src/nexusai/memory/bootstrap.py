"""
Modular Composition Root DI container wiring Memory Engine sub-services.
"""

from __future__ import annotations

from nexusai.memory.config import MemoryEngineConfig
from nexusai.memory.contracts.embedding import EmbeddingProvider
from nexusai.memory.contracts.storage import MemoryStorage
from nexusai.memory.contracts.vector import VectorStore
from nexusai.memory.embedding import (
    LocalEmbeddingProvider,
    MockEmbeddingProvider,
    RemoteEmbeddingProvider,
)
from nexusai.memory.metrics import MemoryMetricsCollector
from nexusai.memory.pipeline import PipelineFactory, RetrievalPipeline
from nexusai.memory.policies import DeduplicationPolicy, PolicyEngine, RetentionPolicy
from nexusai.memory.serializer import JSONMemorySerializer, MemorySerializer
from nexusai.memory.service import MemoryService
from nexusai.memory.services.admin import MemoryAdminService
from nexusai.memory.services.command import MemoryCommandService
from nexusai.memory.services.query import MemoryQueryService
from nexusai.memory.storage import InMemoryMemoryStore, SQLiteMemoryStore
from nexusai.memory.uow import DefaultMemoryUnitOfWork
from nexusai.memory.usecases import (
    ForgetMemoryUseCase,
    RetrieveMemoryUseCase,
    SearchMemoryUseCase,
    StoreMemoryUseCase,
)
from nexusai.memory.vector import ChromaVectorStore, InMemoryVectorStore, MockVectorStore


class StorageModule:
    """Builder module for storage persistence dependencies."""

    @staticmethod
    def build(config: MemoryEngineConfig, serializer: MemorySerializer) -> MemoryStorage:
        if config.storage_dir == ":memory:":
            return InMemoryMemoryStore()
        return SQLiteMemoryStore(db_path=config.get_sqlite_db_path(), serializer=serializer)


class VectorModule:
    """Builder module for vector store dependencies."""

    @staticmethod
    def build(config: MemoryEngineConfig) -> VectorStore:
        if config.vector_provider == "chroma":
            return ChromaVectorStore(
                collection_name=config.vector_collection_name, dimensions=config.vector_dimensions
            )
        elif config.vector_provider == "mock":
            return MockVectorStore(dimensions=config.vector_dimensions)
        return InMemoryVectorStore(dimensions=config.vector_dimensions)


class EmbeddingModule:
    """Builder module for embedding provider dependencies."""

    @staticmethod
    def build(config: MemoryEngineConfig) -> EmbeddingProvider:
        if config.embedding_provider == "local":
            return LocalEmbeddingProvider(
                model_name=config.embedding_model, dimensions=config.vector_dimensions
            )
        elif config.embedding_provider == "remote":
            return RemoteEmbeddingProvider(
                model_name=config.embedding_model, dimensions=config.vector_dimensions
            )
        return MockEmbeddingProvider(
            model_name=config.embedding_model, dimensions=config.vector_dimensions
        )


class PolicyModule:
    """Builder module for MemoryPolicy engines."""

    @staticmethod
    def build(config: MemoryEngineConfig) -> PolicyEngine:
        return PolicyEngine(policies=[RetentionPolicy(), DeduplicationPolicy()])


class PipelineModule:
    """Builder module for retrieval pipelines."""

    @staticmethod
    def build(config: MemoryEngineConfig, vector_store: VectorStore) -> RetrievalPipeline:
        factory = PipelineFactory()
        return factory.create_pipeline(profile_name=config.pipeline_profile)


class MemoryEngineBootstrap:
    """Composition Root bootstrapping Memory Engine using modular builders and sub-services."""

    @staticmethod
    def create_service(config: MemoryEngineConfig | None = None) -> MemoryService:
        cfg = config or MemoryEngineConfig()

        metrics = MemoryMetricsCollector()
        serializer = JSONMemorySerializer()
        storage = StorageModule.build(cfg, serializer)
        vector_store = VectorModule.build(cfg)
        embedder = EmbeddingModule.build(cfg)
        pipeline = PipelineModule.build(cfg, vector_store)
        policy_engine = PolicyModule.build(cfg)

        uow = DefaultMemoryUnitOfWork()
        store_usecase = StoreMemoryUseCase(uow=uow)
        retrieve_usecase = RetrieveMemoryUseCase(uow=uow)
        search_usecase = SearchMemoryUseCase(
            uow=uow, pipeline=pipeline, embedding_provider=embedder
        )
        forget_usecase = ForgetMemoryUseCase(uow=uow)

        command_service = MemoryCommandService(
            store_usecase=store_usecase,
            forget_usecase=forget_usecase,
            storage=storage,
            metrics=metrics,
            uow=uow,
        )
        query_service = MemoryQueryService(
            retrieve_usecase=retrieve_usecase, search_usecase=search_usecase, metrics=metrics
        )
        admin_service = MemoryAdminService(
            storage=storage,
            vector_store=vector_store,
            embedding_provider=embedder,
            pipeline=pipeline,
            policy_engine=policy_engine,
            metrics=metrics,
        )

        service = MemoryService(
            command_service=command_service,
            query_service=query_service,
            admin_service=admin_service,
        )

        return service
