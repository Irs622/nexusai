# ADR 0010: Context Compaction and Memory Retention Architecture

* **Status**: ACCEPTED
* **Context**: Multi-turn agent execution accumulates observations monotonically in `WorkingMemory`. In long-running agent sessions, unbounded observation growth causes context window exhaustion, latency degradation, and high execution costs. Vendor-neutral runtime context budgeting and compaction are required to preserve efficient intelligent execution.
* **Decision**:
  1. Introduce abstract `ContextUnits` and `ContextBudget` (`max_units`, `warning_threshold_ratio`, `critical_threshold_ratio`) decoupled from vendor-specific tokenizers.
  2. Implement `CharacterEstimator` (4 chars = 1 unit) and `ProviderTokenizerEstimator` as pluggable `IContextEstimator` implementations.
  3. Separate `RetentionPolicy` (*what* to retain: `max_active_observations`, `preserve_artifacts`) from `CompactionStrategy` (*how* to compact).
  4. Preserve pure domain `Observation` immutability while tracking runtime lifecycle states (`ACTIVE`, `COMPACTED`, `ARCHIVED`) via `ObservationMetadata` inside `WorkingMemory`.
  5. Structure `CompactionPipeline` as a single-responsibility orchestrator returning an immutable `CompactionResult` delta applied cleanly via `WorkingMemory.apply_compaction(result)`.
  6. **Staged Pipeline Evolution Roadmap (Phase 4 Target)**: Should feature complexity increase (e.g. semantic clustering, LLM summarization, temporal decay), `CompactionPipeline` will evolve into a staged pipeline (`EstimateStage` -> `TriggerStage` -> `ScoreStage` -> `PartitionStage` -> `SummaryStage`) without breaking `CompactionResult` or `WorkingMemory` contracts.
* **Alternatives Considered**:
  - *External Vector Database (Pinecone, ChromaDB)*: Rejected for core runtime memory compaction to preserve vendor-agnostic architecture. Vector DBs belong to long-term knowledge storage.
  - *LLM-driven Monolithic Summarization*: Rejected for core Brain runtime. Core compaction remains deterministic and testable offline.
* **Consequences**:
  - **Positive**: Single-session observation growth remains strictly bounded ($< 1.0\text{ MB}$ delta across 10,000 turns).
  - **Positive**: Zero vendor SDK leakage inside `src/nexusai/brain/`.
  - **Negative**: Generated context summaries append structured text blocks to scratchpad, requiring clean formatting.
* **Validation Criteria**:
  - `tests/unit/brain/test_context_budget.py`
  - `tests/unit/brain/test_observation_lifecycle.py`
  - `tests/unit/brain/test_importance_policy.py`
  - `tests/unit/brain/test_compaction_pipeline.py`
  - `tests/unit/brain/test_single_session_long_run.py`
* **Review Phase**: Phase 3.3
