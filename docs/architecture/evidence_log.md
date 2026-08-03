---
status: active
audience:
  - architects
  - core-developers
owner:
  - core-team
applies_to:
  - repository-wide
review_cycle: weekly
last_reviewed: 2026-08-04
---

# 🔬 Chronological Architecture Evidence Log

This log records real-world empirical observations, API behavioral evidence, and design decisions triggered by actual provider adapter implementations.

---

## 📅 Chronological Evidence Journal

### 2026-08-04: OpenRouter Adapter L5 Validation Complete
- **Evidence Observed**: OpenRouter API (`https://openrouter.ai/api/v1`) executed Level 1 API Surface, Level 2 Behavior, and Fault Injection suites with 0 core kernel mutations.
- **Pain Points Discovered**:
  - `PP-001`: Reasoning/Thinking tokens unmapped (`Usage.completion_tokens_details.reasoning_tokens`)
  - `PP-002`: Stream Delta finish_reason timing (emitted in final `[DONE]` chunk)
  - `PP-003`: Rate Limit Retry-After header parsing
- **Decisions Taken**:
  - `RA-001` (ContextCache) retained as `REJECTED` (Pending Gemini evidence)
  - `RA-002` (reasoning_tokens) retained as `REJECTED` (Pending Gemini evidence)
  - Kernel abstractions frozen at `v1.0.0`
- **Affected Modules**: `src/nexusai/providers/openrouter/` only (0 kernel changes)
