---
status: active
audience:
  - architects
  - core-developers
owner:
  - core-team
applies_to:
  - provider-adapters
review_cycle: weekly
last_reviewed: 2026-08-04
---

# 📝 Categorized Provider SDK Pain Point Log

This log tracks unmapped vendor features, wire format friction, or SDK limitations encountered during adapter implementations.

> **Immutable Governance Directive**: Kernel abstractions in `nexusai.runtime` and `nexusai.providers` ARE LOCKED during adapter implementations. Refactoring is ONLY permitted when a pain point is verified as `Shared = YES` across at least TWO real provider implementations.

---

## 📊 Cross-Provider Pain Point Decision Matrix (Post-Ollama Sprint 4 Review)

| Pain Point ID | Category | OpenRouter | Gemini | Anthropic | Ollama | Shared? | Decision / Action |
|---|---|---|---|---|---|---|---|
| **PP-001** (Reasoning Tokens) | `Reasoning` | ✓ YES | ✓ YES | ✓ YES | ✗ NO | **YES** | **RESOLVED (Sprint 5)** |
| **PP-002** (Stream Delta Finish Timing) | `Streaming` | ✓ YES | ✗ NO | ✓ YES | ✓ YES | **YES** | **RESOLVED (Sprint 5)** |
| **PP-003** (Retry-After Header Parsing) | `Rate Limit` | ✓ YES | ✗ NO | ✓ YES | ✗ NO | **YES** | **RESOLVED (Sprint 5)** |
| **PP-004** (Gemini Candidates Token Count) | `Cost` | ✗ NO | ✓ YES | ✗ NO | ✗ NO | **NO** | `IGNORE` (Vendor specific) |

---

## 📋 Pain Point Inventory

### PP-001: Reasoning / Thinking Tokens Unmapped
- **ID**: `PP-001`
- **Category**: `Reasoning`
- **Providers**: OpenRouter (`deepseek-r1`), Gemini (`thinkingConfig`), Anthropic (`thinking`)
- **Severity**: Medium
- **Frequency**: High (for reasoning models)
- **Shared?**: `YES` (Validated across OpenRouter + Gemini + Anthropic)
- **Status**: `RESOLVED (Sprint 5 — Usage.reasoning_tokens normalized)`

### PP-002: Stream Delta Finish Reason Timing
- **ID**: `PP-002`
- **Category**: `Streaming`
- **Providers**: OpenRouter, Anthropic, Ollama
- **Severity**: Low
- **Frequency**: Always (100% of stream responses)
- **Shared?**: `YES` (Validated across OpenRouter + Anthropic + Ollama)
- **Status**: `RESOLVED (Sprint 5 — StreamController finish_reason timing standardized)`

### PP-003: Rate Limit Retry-After Header Parsing
- **ID**: `PP-003`
- **Category**: `Rate Limit`
- **Providers**: OpenRouter, Anthropic
- **Severity**: Medium
- **Frequency**: Moderate (only under rate limits)
- **Shared?**: `YES` (Validated across OpenRouter + Anthropic)
- **Status**: `RESOLVED (Sprint 5 — ProviderRateLimitError.retry_after header parsing implemented)`

