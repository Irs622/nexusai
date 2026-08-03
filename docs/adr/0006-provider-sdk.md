---
status: accepted
audience:
  - architects
  - contributors
owner:
  - core-team
applies_to:
  - provider-sdk
review_cycle: yearly
last_reviewed: 2026-08-04
---

# ADR 0006: Vendor-Agnostic Provider SDK Architecture

## Context

To function as a true AI Operating System, NexusAI must support diverse LLM providers (OpenAI, Anthropic, Gemini, OpenRouter, 9Router, Ollama, Azure OpenAI, local servers) without coupling application runtime or reasoning logic to specific vendor APIs. Direct integration with specific vendor schemas creates severe technical debt, fragile code paths, and security vulnerabilities (e.g., accidental API key leakage in raw responses or configs).

## Decision

We establish a vendor-agnostic **Provider SDK Foundation** under `nexusai.providers` governed by the **Adapter Pattern** and strict separation of concerns across application layers.

### 1. Architectural Stack

```text
Application / CLI / Web
          │
          ▼
   Reasoning Engine
          │
          ▼
   ProviderPolicy (Cost, Latency, Capability, Privacy, Availability)
          │
          ▼
   ProviderRouter (Policy Delegation & Route Execution)
          │
          ▼
   ProviderProfileCache (Cached Latency, Cost, Reliability Metrics)
          │
          ▼
   ProviderManager (Lifecycle, Health, Metrics, Capability Queries)
          │
          ▼
   ProviderRegistry (Instance Storage & Lookups)
          │
          ▼
      BaseProvider (SDK Abstract Base Interface)
          │
  ┌───────┼───────────┬──────────────┬─────────────┐
  │       │           │              │             │
OpenAI  Anthropic  OpenRouter     9Router       Ollama
Adapter Adapter    Adapter        Adapter       Adapter
```

### 2. Strong Data Contracts & Schema Isolation

- **No Vendor Leakage**: Public methods use strongly-typed contracts (`ChatRequest`, `ChatResponse`, `EmbeddingResult`) instead of raw `dict[str, Any]`.
- **Multi-Choice Support**: `ChatResponse` wraps `choices: list[ChatChoice]` to support multi-candidate responses natively across models.
- **Explicit Accessors**: Candidates are accessed via explicit methods (`response.primary_choice()`, `response.best_choice()`).
- **Enum Type Safety**: Standardized `MessageRole` (`SYSTEM`, `USER`, `ASSISTANT`, `TOOL`, `DEVELOPER`) prevents case/string typos.
- **First-Class Domain Specifications**: `JSONSchema` is established as a first-class domain model used by `ToolSchema`, `ChatRequest.response_format`, and structured outputs.
- **Isolated Debug Traces**: Provider metadata trace data is captured via `ProviderTrace` rather than exposing raw vendor dictionaries.

### 3. Capability Spectrum & Health Monitoring

- Capabilities are declared using the `Capability` enum and `CapabilityLevel` spectrum (`NONE`, `BASIC`, `ADVANCED`, `NATIVE`).
- Provider health metrics are encapsulated in `ProviderHealth` (tracking status, latency, errors, model counts).

### 4. Separation of Management, Health, & Routing

- `ProviderRegistry`: Pure instance registration and lookup. Instance-based to support isolation during testing.
- `ProviderManager`: Lifecycle management (`initialize_all`, `shutdown_all`).
- `HealthMonitor`: Dedicated background health check monitoring service (`start()`, `stop()`, `check_all()`).
- `ProviderRouter`: Policy pipeline runner (`route(policy=...)`) executing policy evaluation rules.
- `BaseProviderPolicy`: Evaluates providers with `PolicyResult(allow, score, reason)` supporting weighted policy scoring.

### 5. Middleware Pipeline Architecture (`BaseMiddleware`)

Middleware chain (`MiddlewarePipeline`) intercepts `ChatRequest` and `ChatResponse` processing around provider execution:
- Logging & Tracing
- Retry Strategies (`RetryPolicy`)
- PII Masking & Cost Tracking
- Tracing & Metrics

### 7. Runtime Execution Kernel Primitives

- **Structured Execution Context**: `ExecutionContext` aggregates `RequestContext`, `TraceContext`, `RuntimeContext`, and `ResourceContext` to eliminate God Object antipatterns.
- **Hierarchical Cancellation Model**: `CancellationToken` supports parent-child relationships so task branch cancellations propagate cleanly down subtasks.
- **Unified Deadline Model**: `Deadline` calculates remaining seconds and expiration state across nested workflow boundaries.
- **Structured Resource Budget**: `ExecutionBudget` specifies `token_budget`, `money_budget`, `time_budget`, `tool_budget`, and `retry_budget`.
- **System Clock Abstraction**: `Clock` and `TestClock` enable deterministic time travel and instant sleep in unit testing.
- **Runtime Task State Machine**: `ExecutionState` and `ExecutionStateMachine` enforce valid state transitions (`CREATED` ➔ `QUEUED` ➔ `RUNNING` ➔ `COMPLETED`/`FAILED`/`CANCELLED`).
- **Circuit Breaker Protection**: `CircuitBreaker` guards provider endpoints against cascading failures using `CLOSED`, `OPEN`, and `HALF_OPEN` states.
- **Error Classification & Retry Decider**: `RetryDecider` enforces error classification tables (retrying timeout/network/rate-limit errors while rejecting auth/config errors).
- **Fine-Grained Error Taxonomy**: `ProviderAuthenticationError`, `ProviderRateLimitError`, `ProviderTimeoutError`, `ProviderNetworkError`, and `ProviderCircuitOpenError` decouple failure domains.

## Consequences

- **Positive**: Complete vendor independence and enterprise AI OS kernel infrastructure (middleware chain, execution contexts, cancellation tokens, circuit breakers, exponential retries, stateful sessions, background health monitoring, EWMA metrics, event bus integration).
- **Positive**: Strict static typing guarantees compliance across the entire codebase (`mypy --strict`).
- **Negative**: Adapter implementations must explicitly map vendor-specific wire formats into canonical NexusAI data models.


