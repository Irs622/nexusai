# ADR 0005: Pluggable ReasoningEngine and Immutable Observation Layer

- **Status**: Accepted
- **Date**: 2026-08-03
- **Authors**: NexusAI Core Team

## Context & Problem Statement
Direct coupling between reasoning logic and specific LLM providers makes strategy migration difficult. Furthermore, evaluating raw tool strings introduces complex error-handling branching.

## Decision Outcome
1. **`InferenceService` Indirection**: `ReasoningEngine` invokes `InferenceService`, which routes requests through `ProviderRouter`.
2. **Unified `Observation` Event Record**: All tool executions, provider timeouts, and policy decisions emit frozen `Observation` events.
