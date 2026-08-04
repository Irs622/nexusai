---
status: accepted
audience:
  - architects
  - contributors
owner:
  - core-team
applies_to:
  - provider-sdk
  - canonical-models
review_cycle: yearly
last_reviewed: 2026-08-04
---

# ADR 0007: Governance Principles for Canonical Model Evolution

## Context

As the NexusAI SDK expands across multiple LLM provider adapters (OpenRouter, Gemini, Anthropic, Ollama, and future providers such as Grok, Mistral, Bedrock, and Azure OpenAI), there is a constant temptation to prematurely introduce vendor-specific fields into canonical models (`ChatRequest`, `ChatResponse`, `Usage`, `ChatMessage`).

Extending canonical domain abstractions without strict cross-provider evidence creates API fragility, forces breaking changes across minor versions, and distorts the semantic meaning of data fields across different vendor implementations.

## Decision

We establish four immutable governance principles for evolving canonical SDK models under `nexusai.providers`:

### 1. Multi-Provider Evidence Requirement
No new canonical field or abstraction may be added to core SDK dataclasses (`Usage`, `ChatMessage`, `ChatChoice`, `ChatRequest`, `ChatResponse`) unless it is natively supported by at least **TWO** independent provider implementations. Single-vendor features MUST remain in vendor-specific metadata (`request.extra_params` or `response.trace`).

### 2. Multi-Vendor Origin Guarantee
Canonical abstractions MUST NOT originate from or mimic a single vendor's API wire format. Normalization must synthesize a clean, vendor-neutral interface that represents the underlying domain domain concept rather than vendor terminology.

### 3. Strict Semantic Accuracy
Canonical fields MUST NEVER alter, distort, or misrepresent raw vendor data semantics.
* *Example*: Mapping Ollama's `eval_count` (which measures general output completion tokens) to `Usage.reasoning_tokens` is prohibited because the semantics differ. If a vendor does not provide an explicit metric for a canonical field, the field MUST default to 0 or `None` rather than substituting an unrelated metric.

### 4. Mandatory Semantic Equivalence Testing
Every canonical model enhancement or translator modification MUST be validated against the `test_canonical_equivalence.py` test suite. The suite enforces **semantic equivalence** (consistent domain semantics for content, finish reasons, usage totals, tool calls, and error taxonomy) across all registered vendor translators.

## Consequences

- Prevents API creep and contract fragility as the SDK grows to 10+ providers.
- Ensures zero breaking changes in canonical SDK public contracts.
- Guarantees clean, evidence-based refactoring during every sprint cycle.
