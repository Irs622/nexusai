# NexusAI Memory Engine Architecture & Sequence Specifications

Phase 2.4 — Memory Runtime Engine Architecture Reference

---

## 🏛️ Subsystem Boundary & Architecture Layering

```text
Brain / Application Layer
          │
          ▼
    MemoryService  (Public API Facade)
          │
          ├── StoreMemoryUseCase
          ├── RetrieveMemoryUseCase
          ├── SearchMemoryUseCase
          └── ForgetMemoryUseCase
                  │
                  ▼
          MemoryUnitOfWork  (Transaction Boundary)
          ├── MemoryRecordRepository  ──>  SQLiteMemoryStore / FileMemoryStore
          ├── VectorRepository        ──>  InMemoryVectorStore / ChromaVectorStore
          └── OutboxRepository        ──>  OutboxDispatcher ──> EventBus
```

---

## 🔄 Sequence Diagrams

### 1. Store Memory Flow
```text
Client -> MemoryService: store(raw_text, scope, type)
MemoryService -> StoreMemoryUseCase: execute(...)
StoreMemoryUseCase -> EmbeddingProvider: embed_text(raw_text)
EmbeddingProvider --> StoreMemoryUseCase: vector_embedding
StoreMemoryUseCase -> MemoryUnitOfWork: async with uow.transaction():
MemoryUnitOfWork -> MemoryRecordRepository: add(record)
MemoryUnitOfWork -> VectorRepository: upsert(vector_record)
MemoryUnitOfWork -> OutboxRepository: enqueue(MemoryStoredEvent)
MemoryUnitOfWork -> Commit: commit transaction
MemoryService --> Client: MemoryRecord
```

### 2. Retrieval Search Pipeline Flow
```text
Client -> MemoryService: search(query, top_k)
MemoryService -> SearchMemoryUseCase: execute(...)
SearchMemoryUseCase -> EmbeddingProvider: embed_text(query)
SearchMemoryUseCase -> RetrievalPipeline: execute(RetrievalContext)
RetrievalPipeline -> Vector Pruning Stage: top-k similarity search
RetrievalPipeline -> Metadata Filter Stage: filter scope, owner, tags, TTL
RetrievalPipeline -> Recency Boost Stage: apply time decay weighting
RetrievalPipeline -> Importance Stage: apply metadata importance
RetrievalPipeline -> Weighted Scoring Stage: calculate sum(feature * weight)
RetrievalPipeline -> Ranking Stage: sort by score descending
RetrievalPipeline -> ContextBuilder: format via PromptFormatter (Markdown/JSON/XML/Claude/OpenAI)
RetrievalPipeline --> MemoryService: QueryResult + PipelineTrace
MemoryService --> Client: QueryResult
```

---

## 🔒 20 AST Architecture Rules Summary (A001–A020)
- **A009**: Domain layer depends EXCLUSIVELY on Python standard library.
- **A010**: Repositories DO NOT import other repositories directly.
- **A011**: Storage engines DO NOT import embedding providers.
- **A012**: UseCases DO NOT import concrete storage implementations.
- **A013**: Kernel DOES NOT import memory module.
- **A014**: RetrievalPipeline remains immutable.
- **A015**: Embedding Provider DOES NOT import VectorStore.
- **A016**: VectorStore DOES NOT import Storage.
- **A017**: Serializer DOES NOT import Repository.
- **A018**: UseCase DOES NOT import concrete Provider directly.
- **A019**: Compliance test suites DO NOT import implementation except target test.
- **A020**: PipelineFactory DOES NOT instantiate provider.
