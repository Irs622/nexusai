---
status: active
audience:
  - architects
  - core-developers
owner:
  - core-team
applies_to:
  - provider-sdk
review_cycle: biweekly
last_reviewed: 2026-08-04
---

# 🛑 Rejected Abstractions Registry

This registry documents proposed architecture abstractions that were explicitly REJECTED to prevent premature over-engineering and architecture creep.

> **Immutable Governance Rule**: No proposed abstraction can be accepted into `nexusai.runtime` or `nexusai.providers` unless it is required by at least TWO real provider implementations.

---

## 📋 Rejected Abstraction Inventory

### RA-001: Explicit `ContextCache` / `cached_tokens` Abstraction
- **Proposed Name**: `ContextCache` / `Usage.cached_tokens`
- **Proposed By**: Provider Integration Review
- **Reason for Rejection**: Supported natively by Gemini and Anthropic, but vendor formats vary.
- **Decision**: `DEFERRED TO SPRINT 6+ — Pending broader provider adoption`
- **Current Workaround**: Pass vendor-specific parameters via `request.extra_params`

### RA-002: `Usage.reasoning_tokens` Field & `reasoning_content` Text
- **Proposed Name**: `Usage.reasoning_tokens` (metric) and `ChatMessage.reasoning_content` (text)
- **Proposed By**: OpenRouter Pain Point `PP-001`
- **Decision**:
  - `Usage.reasoning_tokens` metric: `ACCEPTED (Sprint 5)` — Validated across OpenRouter, Gemini, Anthropic.
  - `ChatMessage.reasoning_content` text string: `DEFERRED TO SPRINT 6+` — Pending vendor thinking format convergence.

### RA-003: `HeaderRetryAfterStrategy`
- **Proposed Name**: `HeaderRetryAfterStrategy`
- **Proposed By**: OpenRouter Pain Point `PP-003`
- **Decision**: `ACCEPTED (Sprint 5)` — Integrated directly into `ProviderRateLimitError.retry_after` and `CanonicalErrorMapper`.
