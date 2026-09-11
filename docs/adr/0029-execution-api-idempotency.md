---
status: accepted
audience:
  - ai-agents
  - contributors
  - security-team
  - runtime-team
owner:
  - runtime-team
applies_to:
  - src/nexusai/infrastructure/idempotency.py
  - src/nexusai/bus/commands.py
  - src/nexusai/brain/planner/engine.py
  - src/nexusai/api/server.py
review_cycle: quarterly
last_reviewed: 2026-09-12
---

# ADR 0029: Execution API Idempotency and State Machine

## Status
Accepted

## Context
In an autonomous agent runtime capable of terminal execution, file manipulation, and orchestrating multi-step Directed Acyclic Graphs (DAGs), duplicate execution presents severe operational and security risks:
1. **Network Retries & Timeouts**: If a client, webhook sender, or network gateway experiences a transient network drop or read timeout, automatic HTTP retries on non-idempotent endpoints (`POST /api/tools/execute`, `POST /api/v1/dag/execute`) can re-execute mutating commands multiple times (e.g., executing shell scripts, creating duplicate database records, or double-allocating resources).
2. **Missing Identity Boundary**: Using a naive global UUID or client-provided key without tenant isolation risks cross-tenant execution collision or reference leakage.
3. **Payload Drift Vulnerabilities**: If an attacker or misconfigured client reuses an idempotency key with a mutated payload (e.g., replaying a key originally used for `git status` to execute `rm -rf /`), absent payload fingerprinting allows malicious payload substitution.
4. **Execution-Layer Bypasses**: Idempotency enforced solely at the HTTP middleware layer does not protect internal dispatch channels such as CQRS CommandBus handlers or autonomous DAG plan re-execution.

## Decision
We implement a robust, identity-scoped execution idempotency subsystem spanning the storage, CQRS command bus, DAG planner engine, and HTTP API layers:

1. **Identity-Scoped Composite Key**:
   - Every idempotency key is strictly scoped by caller identity: `(tenant_id, user_id, idempotency_key)`.
   - In a multi-tenant deployment, Tenant A and Tenant B can safely use identical key strings without collision or cross-tenant data leakage.

2. **Payload Fingerprinting**:
   - Request payloads are canonically serialized (alphabetically sorted keys, compact JSON formatting) and hashed via SHA-256 (`compute_payload_fingerprint`).
   - If a request arrives with the same `(tenant_id, user_id, idempotency_key)` but a different fingerprint, it is immediately rejected with HTTP 409 Conflict (`IdempotencyPayloadMismatchError`).

3. **Explicit State Machine**:
   - Each idempotency record transitions through an explicit lifecycle:
     `PENDING` -> `RUNNING` -> `SUCCEEDED` | `FAILED_TRANSIENT` | `FAILED_TERMINAL` | `CANCELLED` | `EXPIRED`
   - Concurrent duplicate requests during `RUNNING` receive HTTP 409 Conflict with `Retry-After: 2` header (`IdempotencyConflictError`).
   - Replay of `SUCCEEDED` returns cached response with header `X-Cache: HIT`.
   - Replay of `FAILED_TERMINAL` returns cached error with header `X-Cache: HIT`.
   - Replay of `FAILED_TRANSIENT` allows re-execution with the same key.

4. **Concurrency Control & Storage Backends**:
   - `InMemoryIdempotencyStore`: Thread-safe in-memory store utilizing internal locks per composite key.
   - `SqliteIdempotencyStore`: ACID compliant persistent storage backed by SQLite, utilizing unique compound constraints `(tenant_id, user_id, idempotency_key)` with WAL mode.
   - Insert-if-not-exists semantics guarantee atomicity under high-concurrency race conditions.

5. **24-Hour TTL & Expiration**:
   - Default expiration TTL is 24 hours (86,400 seconds), configurable per environment.
   - Expired keys allow clean reuse for subsequent operations.

6. **Response Cache Secret Sanitization**:
   - Stored responses and cached outputs are automatically scrubbed via `sanitize_secrets_recursive()`.
   - No raw API keys, bearer tokens, or sensitive credentials are ever cached.

7. **Multi-Layer Enforcement**:
   - **HTTP API Layer**: Coordinates cache validation, headers (`X-Cache: HIT` / `X-Cache: MISS`), and fast-path responses.
   - **CQRS CommandBus Layer**: `ExecuteToolCommandHandler` validates idempotency at the handler boundary for all tool calls.
   - **DAG Planner Engine Layer**: `PlanGraphExecutionEngine` validates idempotency before compiling and executing plan nodes.

## Alternatives Considered
1. **Redis-Only Idempotency Store**:
   - *Rejected*: NexusAI provides an embedded, self-contained architecture suitable for edge environments. Imposing an external Redis dependency violates zero-dependency standalone operation.
2. **HTTP Middleware-Only Idempotency**:
   - *Rejected*: Does not protect internal execution paths (CQRS command bus, DAG engine, scheduled background tasks).
3. **Optimistic Locking without Fingerprinting**:
   - *Rejected*: Fails to detect payload mutation, creating severe security vulnerabilities if client keys are reused across different operations.

## Consequences
### Positive
- Prevents duplicate tool invocations and duplicate DAG executions during network retries.
- Full tenant and user isolation across all idempotency scopes.
- Secret sanitization ensures cached payloads remain leak-free.
- Pluggable storage architecture allows seamless transition between in-memory and persistent SQLite stores.

### Negative
- Slight memory/disk footprint to persist idempotency records for 24 hours.
- Requires callers to supply unique `Idempotency-Key` headers or parameters when idempotency is desired.

## Validation Criteria
- All 20 unit and integration tests in `tests/unit/infrastructure/test_idempotency.py` pass cleanly.
- Verified concurrent atomicity with 10 parallel requests.
- Verified payload mismatch yields HTTP 409 Conflict.
- Verified secret redaction in cached responses.
- Verified 100/100 architecture compliance score.

## Review Phase
Accepted and implemented in Milestone Phase 3 / Release v1.0.0.
