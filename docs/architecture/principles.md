---
status: stable
audience:
  - architects
  - core-developers
  - contributors
owner:
  - core-team
applies_to:
  - repository-wide
review_cycle: quarterly
last_reviewed: 2026-08-04
---

# 🏛️ NexusAI Architectural Principles

This document defines the 10 immutable architectural directives governing the NexusAI AI Operating System codebase. All AI Agents and human contributors must strictly adhere to these principles.

---

## 1. Interface-Driven Communication
All communication between system modules MUST occur strictly through abstract interfaces or protocol definitions, never directly through concrete implementation classes.

## 2. Inward Dependency Direction (Clean Architecture)
Dependencies MUST strictly point inward toward the core domain layers. High-level domain logic and core policies must never depend on low-level details, adapters, database schemas, or external transport layers.

## 3. Strict Provider Adapter Isolation
No LLM provider adapter (e.g., OpenRouter, Ollama, Gemini, Anthropic) may possess knowledge of, import from, or depend on any other provider adapter.

## 4. Vendor-Agnostic Routing
Routing mechanisms (`ProviderRouter`, `ProviderPolicy`) MUST operate exclusively on canonical SDK domain models (`ChatRequest`, `ChatResponse`, `Capability`) and MUST NOT contain vendor-specific logic or wire format transformations.

## 5. Non-Blocking Asynchronous I/O
All network requests, filesystem access, subprocess calls, and IPC operations MUST be asynchronous (`async`/`await`). No blocking synchronous thread calls may be executed on event loop threads.

## 6. Full Service Replaceability via Dependency Injection
All services (Registry, Router, HealthMonitor, Metrics, Scheduler) MUST be injectable and replaceable via the Service Container (`ServiceContainer`), allowing seamless mocking during testing and custom runtime extensions.

## 7. Provider-Agnostic Middleware
Middleware pipeline components (`BaseMiddleware`) MUST process requests and responses generically using canonical contracts and MUST NOT depend on specific LLM vendors.

## 8. Transport-Independent Domain Models
Core domain models (`ChatMessage`, `ChatChoice`, `JSONSchema`, `ProviderHealth`) MUST remain pure Python dataclasses or Pydantic models with zero dependencies on HTTP frameworks, CLI wrappers, or external client libraries.

## 9. Immutable Telemetry Events
All events emitted over the system event bus (`ProviderEvent`, `RoutingDecisionEvent`, `ProviderHealthChangedEvent`) MUST be strictly immutable data objects (`frozen=True`).

## 10. Test-Driven & ADR-Gated Evolution
Every new component MUST include comprehensive unit tests. Any modification that alters system architecture boundaries, introduces core dependencies, or modifies public contracts MUST be gated by an Architectural Decision Record (ADR) under `docs/adr/`.
