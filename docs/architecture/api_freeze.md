# API Freeze & Governance Policy

## Governance Levels

NexusAI classifies public contracts into three distinct stability tiers:

| Level | Definition | Change Policy | Frozen Objects |
|---|---|---|---|
| **Stable** | Production-grade public API contract | Breaking changes STRICTLY PROHIBITED without ADR approval, major version bump, and snapshot update. | `ExecutionContext`, `ProviderProfile`, `ProviderMetadata`, `ProviderHealth`, `MemoryRecord`, `EmbeddingCapabilities` |
| **Beta** | Feature-complete, evolving API | Backward-compatible changes allowed; breaking changes require migration notice and 1-sprint deprecation. | Memory Pipeline, Vector Repositories, Event Bus Contracts |
| **Experimental** | Active development | Internal design subject to change without deprecation warnings. | Brain Runtime internals, experimental plugins |

---

## Frozen API Surfaces (`Stable` Tier)

The following 6 public contract classes are frozen and covered by golden snapshot regression tests under `tests/api_compatibility/`:

1. **`nexusai.providers.context.ExecutionContext`**
2. **`nexusai.providers.profile.ProviderProfile`**
3. **`nexusai.providers.models.ProviderMetadata`**
4. **`nexusai.providers.models.ProviderHealth`**
5. **`nexusai.memory.domain.record.MemoryRecord`**
6. **`nexusai.memory.contracts.embedding.EmbeddingCapabilities`**

---

## Change Management Workflow for Frozen Surfaces

Any proposed modification to a `Stable` tier object MUST satisfy all 5 requirements:

1. **Architecture Decision Record (ADR)**: Create an approved ADR under `docs/adr/`.
2. **Golden Snapshot Update**: Run `pytest tests/api_compatibility/ --update-snapshots` and commit updated golden JSON files.
3. **CHANGELOG Entry**: Document breaking change, rationale, and migration instructions under `CHANGELOG.md`.
4. **Deprecation Path**: Provide backward-compatible alias or deprecation warning if feasible.
5. **Architecture Review**: Tech lead approval prior to merging PR.
