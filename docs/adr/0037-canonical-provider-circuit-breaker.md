---
status: accepted
audience:
  - contributors
owner:
  - core-team
applies_to:
  - src/nexusai/providers/circuit_breaker.py
  - src/nexusai/runtime/circuit_breaker.py
  - src/nexusai/models/circuit_breaker.py
review_cycle: yearly
last_reviewed: 2026-10-25
---

# ADR 0037: Canonical Provider CircuitBreaker

## Status
Accepted. This is the first step of RFC 0002 (package consolidation).

## Context
Three provider-level `CircuitBreaker` implementations existed:

| Module | Used by | Differences |
|---|---|---|
| `nexusai.providers.circuit_breaker` | `ProviderEngine` | Base state machine, `call()` guard |
| `nexusai.runtime.circuit_breaker` | `runtime.engine`, `nexusai.runtime.__all__` | Same, plus injectable `Clock` |
| `nexusai.models.circuit_breaker` | `models.router.ProviderRouter` | Different API: `can_execute()`, sliding-window metrics, health score, upper-case state values, no success threshold |

`nexusai.runtime` already depends on `nexusai.providers`, and `providers` never imports `runtime`.

The tool-level breaker in `nexusai.brain.runtime.execution_policy` is out of scope. It guards tool execution, not provider calls, and the `brain_isolation` import contract forbids `brain` from importing `nexusai.providers`.

## Decision
- `nexusai.providers.circuit_breaker` is the single canonical implementation. It sits in the lowest layer, so the aliases introduce no import cycles.
- The canonical class absorbs the other two feature sets additively:
  - the injectable `clock` from `runtime`;
  - `can_execute()`, `failure_count`, `total_failures`, `trip_count`, `last_failure_time`, a bounded sliding window (`sliding_window_size`), `calculate_health_score()` and `get_metrics()` from `models`.

  `record_success()` and `record_failure()` gain optional `latency_ms`. `record_failure()`'s `error` becomes optional, and `call()` records measured latency.
- `nexusai.runtime.circuit_breaker` and `nexusai.models.circuit_breaker` become deprecated aliases. Accessing `CircuitBreaker` or `CircuitState` there emits a `DeprecationWarning`.
- The `models` alias returns a thin subclass that keeps that module's former defaults: optional `provider_id`, `success_threshold=1`, and an upper-case `get_metrics()["state"]`.
- `from nexusai.runtime import CircuitBreaker, CircuitState` (public `__all__`) re-exports the canonical class without a warning.

## Alternatives Considered
1. **Canonical in `nexusai.runtime`.** Rejected because `providers.engine` would have to import `runtime`, creating a `providers` ↔ `runtime` cycle.
2. **Keep `models` as a separate implementation.** Rejected because it leaves two state machines with diverging semantics. Its features fit additively into the canonical class.
3. **Fold the `brain` tool breaker in as well.** Rejected because it would violate the `brain_isolation` contract. It needs its own design under RFC 0002.

## Consequences
- **Positive:** One provider breaker to maintain and test. Every user gets deterministic clock injection and health metrics. Existing imports keep working.
- **Negative:** `CircuitState` from `nexusai.models.circuit_breaker` now has lower-case values (`"open"`), so code that compares a legacy breaker's `state` to raw upper-case strings breaks. Comparisons against enum members are unaffected. Each canonical breaker also keeps a bounded window of `sliding_window_size` (default 50) outcome tuples.
- The `clock` parameter is typed as `nexusai.providers.clock.Clock`. `nexusai.runtime.clock` is a duplicate ABC, still to be consolidated under RFC 0002.

## Validation Criteria
- `tests/unit/test_circuit_breaker_canonical.py` covers the lifecycle with an injected clock, trip counting, window bounding, alias warnings and identity, the warning-free `nexusai.runtime` export, and the legacy `models` defaults.
- Existing provider, runtime, contract and architecture tests pass unchanged apart from import paths.

## Review Phase
Remove both alias modules after at least one minor release (AGENTS.md §6). Revisit together with the `runtime.clock` / `providers.clock` duplication.
