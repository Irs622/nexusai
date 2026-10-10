---
status: accepted
date: 2026-10-11
decision-makers:
  - runtime-architect
  - core-team
consulted:
  - contributors
informed:
  - contributors
---

# ADR 0036: Single Tool Call per Model Turn

## Status
Accepted

## Context
`BaseModelProvider.chat()` returns one normalized dict: either `{"type": "text", ...}` or `{"type": "tool_call", "tool_name", "arguments"}`. `BrainCoordinator`, the agent loop, and the LangGraph workflow all consume exactly one tool call per turn.

OpenAI-compatible APIs may return several tool calls in one response (parallel function calling). `OpenAIProvider` used to take `tool_calls[0]` and silently discard the rest (issue #53 / AUDIT-12).

## Decision
- The provider contract stays at **at most one tool call per model turn**.
- `OpenAIProvider` sends `parallel_tool_calls=False` whenever tools are supplied, so the model is asked for one call at a time.
- If a backend ignores the flag and still returns several calls, the provider executes only the first and logs a `WARNING` naming the ignored calls. The agent loop then feeds the result back, and the model can request the remaining calls on later turns.

## Alternatives Considered
1. **Return a list of tool calls.** Rejected for now: it changes a `@stable` public contract consumed by the coordinator, loop executor, workflow nodes, and every provider. That would need a deprecation cycle (AGENTS.md §6).
2. **Raise an error when multiple calls arrive.** Rejected: it would fail user turns on backends that ignore `parallel_tool_calls`.

## Consequences
- **Positive:** Behavior is explicit and observable. There are no silent drops, and no public contract changes.
- **Negative:** Independent tool calls run sequentially across turns, adding one model round-trip per extra call.

## Validation Criteria
- Unit tests assert `parallel_tool_calls=False` is sent when tools are provided and omitted otherwise.
- Unit tests assert a warning is logged and the first call is returned when multiple calls arrive.

## Review Phase
Revisit if multi-call batching becomes a latency requirement; that change needs a new `SchemaVersion`-ed provider response contract.
