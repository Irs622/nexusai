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
| **PP-001** (Reasoning Tokens) | `Reasoning` | ✓ YES | ✓ YES | ✓ YES | ✓ YES | **YES** | **Candidate for Sprint 5 Review** |
| **PP-002** (Stream Delta Finish Timing) | `Streaming` | ✓ YES | ✗ NO | ✓ YES | ✓ YES | **YES** | **Candidate for Sprint 5 Review** |
| **PP-003** (Retry-After Header Parsing) | `Rate Limit` | ✓ YES | ✗ NO | ✓ YES | ✗ NO | **YES** | **Candidate for Sprint 5 Review** |
| **PP-004** (Gemini Candidates Token Count) | `Cost` | ✗ NO | ✓ YES | ✗ NO | ✗ NO | **NO** | `IGNORE` (Vendor specific) |

---

## 📋 Pain Point Inventory

### PP-001: Reasoning / Thinking Tokens Unmapped
- **ID**: `PP-001`
- **Category**: `Reasoning`
- **Providers**: OpenRouter (`deepseek-r1`), Gemini (`thinkingConfig`), Anthropic (`thinking`), Ollama (`deepseek-r1:7b`)
- **Severity**: Medium
- **Frequency**: High (for reasoning models)
- **Workaround**: Currently unmapped in canonical `Usage` model
- **Shared?**: `YES` (Validated across OpenRouter + Gemini + Anthropic + Ollama)
- **Status**: `ACCEPTED FOR SPRINT 5 KERNEL REFACTORING REVIEW`

### PP-002: Stream Delta Finish Reason Timing
- **ID**: `PP-002`
- **Category**: `Streaming`
- **Providers**: OpenRouter, Anthropic, Ollama
- **Severity**: Low
- **Frequency**: Always (100% of stream responses)
- **Workaround**: Handled cleanly in `StreamController.assemble_final_response`
- **Shared?**: `YES` (Validated across OpenRouter + Anthropic + Ollama)
- **Status**: `ACCEPTED FOR SPRINT 5 KERNEL REFACTORING REVIEW`

### PP-003: Rate Limit Retry-After Header Parsing
- **ID**: `PP-003`
- **Category**: `Rate Limit`
- **Providers**: OpenRouter, Anthropic
- **Severity**: Medium
- **Frequency**: Moderate (only under rate limits)
- **Workaround**: Generic `ProviderRateLimitError` handling
- **Shared?**: `YES` (Validated across OpenRouter + Anthropic)
- **Status**: `ACCEPTED FOR SPRINT 5 KERNEL REFACTORING REVIEW`

