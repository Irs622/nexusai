---
status: accepted
validation_phase: Phase 3.2
expected_review: Phase 4.0
audience:
  - architects
  - contributors
owner:
  - core-team
applies_to:
  - brain-runtime
  - core-architecture
related:
  - ADR-0004
  - ADR-0006
  - ADR-0007
review_cycle: yearly
last_reviewed: 2026-08-07
---

# ADR 0008: Stateless Brain Runtime Architecture & Execution Pipeline

## Context

Phase 3.1 establishes the core single-turn orchestration runtime (`nexusai.brain`) bridging Applications to `MemoryRuntime`, `ProviderRuntime`, and `KernelRuntime`. 

To prevent architectural drift and technical debt as the platform evolves toward Phase 3.2 (Agent Runtime) and Phase 4.0 (AI Operating System), clear architectural decisions must be documented explaining the technical rationale behind key system boundaries, rejected alternatives, trade-offs, and validation criteria.

---

## Decisions

### 1. Linear `ExecutionPipeline` over Premature DAG Complexity
We select a linear `ExecutionPipeline` executing an ordered sequence of `IExecutionStage` implementations (`HistoryStage` $\rightarrow$ `PromptStage` $\rightarrow$ `ProviderStage` $\rightarrow$ `PersistenceStage`) following the Open/Closed Principle. Complex DAG graph scheduling is explicitly deferred to Phase 3.2 when multi-branching use cases (fan-out, parallel tool execution, reflection) natively emerge.

### 2. Provider-Encapsulated Capability Negotiation
Brain Runtime requests model capabilities via canonical `RequiredCapabilities` value objects. Matrix lookup, vendor matching, and route strategy resolution are encapsulated within `ProviderRuntime` (`ProviderSelector`). Brain Runtime remains 100% provider-agnostic.

### 3. Canonical Provider-Independent `PromptBundle`
`PromptRenderer` in `nexusai.brain` strictly compiles `AssembledContext` into canonical `PromptBundle` containers (pure semantic messages and polymorphic `Artifact` attachments). Vendor-specific formatting (ChatML, Claude XML, Gemini parts) MUST occur downstream within `ProviderRuntime` adapters.

### 4. Non-Blocking Transactional Outbox Persistence
Turn persistence uses the `IOutboxWriter` port interface delegating to Kernel's transactional outbox (`nexusai.kernel.outbox`). Write-behind persistence tasks run asynchronously out-of-band, guaranteeing storage writes NEVER delay streaming token delivery.

### 5. Polymorphic `ArtifactRegistry`
Multimodal artifacts implement the abstract `Artifact` interface (`kind()`, `size_bytes()`, `validate()`, `to_dict()`). Deserialization uses a dynamic `ArtifactRegistry` factory, preventing `if/elif` type discriminator branching.

### 6. Public Contract Versioning
All public wire payloads, domain entities, and event payloads carry explicit `SchemaVersion(major, minor)` fields with semantic compatibility methods (`supports`, `can_read`).

---

## Alternatives Considered

### Alternative A: Full DAG Graph Engine (`ExecutionGraph`)
- **Description**: Implementing a directed acyclic graph execution engine for Phase 3.1.
- **Status**: Rejected.
- **Rationale**: Premature overengineering for a single-turn runtime. Adds unnecessary complexity and performance overhead before fan-out or multi-tool parallel use cases actually exist.

### Alternative B: Vendor-Specific Prompt Rendering in Brain Runtime
- **Description**: Generating OpenAI ChatML or Claude XML formatting directly inside `nexusai.brain`.
- **Status**: Rejected.
- **Rationale**: Creates strong vendor lock-in, duplicates logic across subsystems, and forces breaking changes in Brain Runtime whenever provider wire formats mutate.

### Alternative C: Synchronous Direct Memory Writes
- **Description**: Awaiting database storage writes before finishing the token generation response to clients.
- **Status**: Rejected.
- **Rationale**: Causes severe latency spikes and increases Time-To-First-Token (TTFT). Decoupled transactional outbox write-behind guarantees persistence without blocking streaming responses.

---

## Consequences

### Positive
- **Provider Independence**: New LLM providers can be added without altering `nexusai.brain`.
- **Low TTFT Latency**: Direct streaming and non-blocking outbox writes preserve sub-millisecond execution overhead.
- **High Testability**: Decoupled ports (`IHistoryProvider`, `IOutboxWriter`) allow pure unit testing without spinning up databases.
- **Stable Public API**: Public contracts use versioned immutable dataclasses with strict schema governance.

### Negative / Trade-Offs
- **No Parallel Stages**: The linear `ExecutionPipeline` cannot execute parallel DAG branches (e.g. concurrent tool execution) without stage refactoring in Phase 3.2.
- **ExecutionContext Growth Risk**: `ExecutionContext` must be carefully monitored to prevent it from becoming a God Object as Agent Runtime adds state fields.
- **No Native Vendor Extensions**: `PromptBundle` cannot express proprietary vendor features directly without adapter translation.

---

## Validation & Revisit Criteria

This ADR remains valid and accepted IF:
1. **Agent Runtime (Phase 3.2)** can be implemented on top of `TurnExecutor` without replacing `ExecutionPipeline` or breaking core contracts.
2. **New LLM Provider Adapters** can be added requiring changes ONLY within `nexusai.providers`.
3. **`PromptBundle`** remains 100% vendor-neutral across all implementations.

*If any of these criteria are violated during Phase 3.2 development, this ADR MUST be formally reopened and revisited.*
