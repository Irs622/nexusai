# 19. Distributed Semantic Memory Adapters: PostgreSQL pgvector & Qdrant

- **Status**: Approved
- **Deciders**: Core Architecture Team, OSPO Maintainer
- **Date**: 2026-09-10
- **Review Phase**: Phase 7 / Level 4 Milestone (Issue #19)

---

## Context

In NexusAI's initial memory subsystem (governed by ADR 0002 and ADR 0012), semantic vector indexing relied primarily on in-process `InMemoryVectorStore` and embedded `ChromaVectorStore`.

While embedded and in-memory vector engines are optimal for zero-dependency local development and single-process CLI usage, multi-worker autonomous agent meshes and production Kubernetes deployments encounter key operational bottlenecks:
1. Embedded storage engines cannot be shared across horizontally scaled worker nodes or distributed containers without file-locking contention.
2. In-process vector indexing lacks production-grade durability, point-in-time recovery, and multi-tenant partitioning at scale.
3. High-throughput semantic retrieval across tens of thousands of memory embeddings requires specialized approximate nearest neighbor (ANN) indexes such as HNSW (*Hierarchical Navigable Small World*) and IVFFlat.

---

## Decision

We introduce two production-grade distributed vector database adapters conforming to the canonical `VectorStore` contract under `nexusai.memory.vector`:

1. **PostgreSQL pgvector Adapter (`PgVectorStore`)**:
   - Uses `asyncpg` with asynchronous connection pooling (`asyncpg.create_pool(min_size=1, max_size=10)`).
   - Automatically bootstraps the `vector` extension and creates target schema tables with JSONB metadata indexing.
   - Supports configurable ANN indexing: HNSW (`m = 16, ef_construction = 64`) for high recall / low query latency, and IVFFlat (`lists = 100`) for memory-constrained environments.
   - Leverages native vector operators: `<=>` (Cosine distance), `<->` (Euclidean distance), and `<#>` (Inner product), paired with JSONB `@>` metadata filtering.

2. **Qdrant Vector Database Adapter (`QdrantVectorStore`)**:
   - Built on `AsyncQdrantClient` for asynchronous gRPC/HTTP operations.
   - Deterministically maps arbitrary string record IDs to RFC 4122 UUIDs via `uuid.uuid5(uuid.NAMESPACE_DNS, f"{namespace}:{record_id}")`, while preserving the canonical `record_id` and payload attributes.
   - Configures collections with `Distance.COSINE` and native HNSW indexing.
   - Dispatches vector searches filtered by namespace and custom metadata.

3. **Graceful High-Availability Fallback**:
   - Both stores implement transparent fallback to `InMemoryVectorStore` when drivers (`asyncpg` / `qdrant-client`) are omitted or database credentials are unset, ensuring zero disruption to local developer workflows.

4. **Composition Root & Config Integration**:
   - Extended `MemoryEngineConfig` with `pgvector_dsn`, `pgvector_table_name`, `pgvector_index_type`, `qdrant_url`, `qdrant_api_key`, `qdrant_collection_name`, and `vector_fallback_enabled`.
   - Wired seamlessly into `VectorModule.build()` inside `src/nexusai/memory/bootstrap.py`.

---

## Alternatives Considered

1. **Weaviate / Milvus / Pinecone**:
   - *Considered*: External SaaS or specialized vector engines.
   - *Decision*: PostgreSQL `pgvector` and `Qdrant` represent the most prevalent open-source, self-hostable standards for enterprise Kubernetes and local Docker Compose deployments. Additional SaaS providers can be introduced via the same `VectorStore` interface in the future.
2. **Synchronous psycopg2 / SQLAlchemy**:
   - *Rejected*: Blocking drivers violate the cooperative multitasking model of NexusAI's asynchronous event loops. Using `asyncpg` and `AsyncQdrantClient` guarantees non-blocking execution under heavy concurrency.

---

## Consequences

### Positive
- Production-ready semantic memory for distributed multi-agent clusters.
- 100% compliance with existing `VectorStore` interface and `VectorComplianceSuite`.
- Zero architectural DAG violations: `nexusai.memory.vector` remains decoupled from higher layers.
- High recall and sub-25ms ANN search latency at enterprise scale.

### Negative
- Requires deploying external database services (PostgreSQL with `pgvector` extension or Qdrant daemon) for distributed deployments.
- Adds optional driver dependencies (`asyncpg`, `qdrant-client`).

---

## Validation Criteria

1. **Compliance Test Suite**: Both `PgVectorStore` and `QdrantVectorStore` pass 100% of the assertions in `VectorComplianceSuite`.
2. **Multi-Tenant Isolation**: Vectors in different namespaces never leak across search queries.
3. **Graceful Fallback**: Missing drivers or unset connection URLs trigger safe in-memory fallback without crashing the runtime.
4. **Static Verification**: Passes `ruff check`, `black --check`, and `mypy --strict`.
