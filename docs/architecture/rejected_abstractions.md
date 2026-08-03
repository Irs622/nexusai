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

### RA-001: Explicit `ContextCache` Abstraction
- **Proposed Name**: `ContextCache`
- **Proposed By**: Provider Integration Review
- **Reason for Rejection**: Currently only Google Gemini natively supports prompt context caching. OpenRouter does not expose explicit context cache controls in its unified API.
- **Decision**: `REJECTED — Pending second provider requirement (e.g. Anthropic Prompt Caching)`
- **Current Workaround**: Pass vendor-specific parameters via `request.metadata`

### RA-002: Vendor-Specific `ReasoningToken` Field in `Usage` Model
- **Proposed Name**: `Usage.reasoning_tokens`
- **Proposed By**: OpenRouter Pain Point `PP-001`
- **Reason for Rejection**: Only OpenRouter/DeepSeek-R1 currently expose `reasoning_tokens` in completion details.
- **Decision**: `REJECTED — Pending Gemini and Anthropic comparison`
- **Current Workaround**: Retain in raw response trace metadata

### RA-003: `HeaderRetryAfterStrategy`
- **Proposed Name**: `HeaderRetryAfterStrategy`
- **Proposed By**: OpenRouter Pain Point `PP-003`
- **Reason for Rejection**: Standard `RetryPolicy` and `CanonicalErrorMapper` already handle HTTP 429 rate limit exceptions sufficiently.
- **Decision**: `REJECTED — Pending second provider evidence`
- **Current Workaround**: Standard exponential backoff with jitter
