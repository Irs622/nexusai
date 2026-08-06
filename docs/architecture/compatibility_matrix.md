# NexusAI API & Version Compatibility Matrix

## Release Compatibility Status

| NexusAI Version | Status | Contract Compatibility | Migration Action |
|---|---|---|---|
| **0.1.0-alpha** (Current) | Active Alpha | Initial Core & Kernel API | N/A (Baseline) |
| **0.2.0** (Target Phase 3) | Planned | Backward compatible with 0.1.0 `Stable` contracts | Automatic / Transparent |
| **1.0.0** (Production) | Planned LTS | Stable frozen contracts guaranteed | Major deprecation cycle |

---

## Model Evolution Log

| Version | Target Object | Change Type | Summary & Rationale |
|---|---|---|---|
| 0.1.0 | `ProviderProfile` | Structural | Refactored from flat parameters to composite `metadata: ProviderMetadata` |
| 0.1.0 | `ExecutionContext` | Structural | Moved cancellation token into sub-context `ctx.runtime.cancellation_token` |
| 0.1.0 | `EmbeddingCapabilities` | Renaming | `max_dimension` renamed to `dimensions` for cross-provider alignment |
| 0.1.0 | `ModelInfo` | Identifier | `name` attribute replaced by `id` + `display_name` |
| 0.1.0 | `ProviderHealth` | Field | `model_count` attribute updated to `available_models` |
