---
status: accepted
audience:
  - ai-agents
  - contributors
  - security-team
  - runtime-team
owner:
  - security-team
applies_to:
  - src/nexusai/brain/domain/audit.py
  - src/nexusai/brain/ports/audit_store_port.py
  - src/nexusai/infrastructure/persistence/sqlite_audit_store.py
  - src/nexusai/infrastructure/persistence/postgres_audit_store.py
  - src/nexusai/api/server.py
review_cycle: quarterly
last_reviewed: 2026-09-12
---

# ADR 0030: Durable Append-Only Audit Log with Cryptographic Tamper Evidence

## Status
Accepted

## Context
Prior to this architectural enhancement, the NexusAI audit chain resided in `app.state.audit_chain` as an in-memory Python list within the FastAPI application state. This posed significant operational and security limitations:
1. **Process Volatility**: A process restart, worker reload, or pod rescheduling resulted in total loss of historical audit records, replacing the ledger with a fresh demo chain.
2. **Unguarded Mutation Endpoints**: Two mutation endpoints (`POST /api/v1/audit/tamper` and `POST /api/v1/audit/reset`) were exposed unconditionally in all execution modes. Intended for visual demonstration of cryptographic tripwire detection, their presence in production environments directly contradicted the system's guarantee of an immutable cryptographic audit ledger.
3. **Missing Durable Append-Only Storage**: Although SHA-256 hash-chaining (`AuditEvent` with `previous_event_hash` linkage) was architecturally modeled, lack of durable append-only persistence meant the system provided tamper detection without durability guarantees.
4. **Tenant-Scoped Ledger Invariants**: Multi-tenant isolation established in Issue #31 required audit events and hash chains to be strictly partitioned by caller identity (`tenant_id`), ensuring cross-tenant audit event leakage or sequence collision is impossible at the persistence layer.

## Decision
We implement a durable append-only cryptographic audit logging subsystem backed by SQLite WAL mode and enforced across the persistence, domain, and API layers:

1. **Durable Append-Only Schema & Zero Mutation Invariant**:
   - Audit events are persisted to a durable SQLite database using write-ahead logging (`PRAGMA journal_mode=WAL;`) with high-concurrency serialized appends.
   - The database schema strictly enforces:
     ```sql
     CREATE TABLE IF NOT EXISTS audit_events (
         id TEXT PRIMARY KEY,
         sequence INTEGER NOT NULL,
         timestamp REAL NOT NULL,
         event_type TEXT NOT NULL,
         actor TEXT NOT NULL,
         tenant_id TEXT NOT NULL DEFAULT 'default',
         tool_name TEXT,
         outcome TEXT NOT NULL,
         metadata_json TEXT NOT NULL DEFAULT '{}',
         previous_hash TEXT NOT NULL,
         event_hash TEXT NOT NULL,
         session_id TEXT NOT NULL DEFAULT '',
         execution_id TEXT NOT NULL DEFAULT '',
         plan_fingerprint TEXT NOT NULL DEFAULT '',
         node_id TEXT,
         worker_id TEXT,
         fencing_token INTEGER,
         severity TEXT NOT NULL DEFAULT 'INFO',
         event_id TEXT GENERATED ALWAYS AS (id) STORED,
         sequence_number INTEGER GENERATED ALWAYS AS (sequence) STORED,
         tool_id TEXT GENERATED ALWAYS AS (tool_name) STORED,
         previous_event_hash TEXT GENERATED ALWAYS AS (previous_hash) STORED,
         metadata TEXT GENERATED ALWAYS AS (metadata_json) STORED,
         CHECK (sequence > 0)
     );
     CREATE INDEX IF NOT EXISTS idx_audit_tenant_seq ON audit_events(tenant_id, sequence);
     CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_events(timestamp);
     CREATE INDEX IF NOT EXISTS idx_audit_event_type ON audit_events(event_type);
     ```
   - **Zero UPDATE / DELETE Invariant**: The store code contains zero `UPDATE` and zero `DELETE` SQL statements targeting `audit_events`. All records are strictly append-only.

2. **Guarded Mutation Endpoints**:
   - `POST /api/v1/audit/tamper` and `POST /api/v1/audit/reset` are disabled by default in production.
   - Guarded by environment variable `NEXUSAI_STUDIO_DEMO_MODE=true`.
   - In production mode, both endpoints return HTTP 403 Forbidden with exact diagnostic message:
     `"Audit log mutation endpoints are disabled in production mode. Set NEXUSAI_STUDIO_DEMO_MODE=true for demonstration environments."`
   - In demo mode, mutation operations affect only an isolated in-memory session chain (`app.state.demo_audit_chains`), never mutating the persistent SQLite audit store.
   - A critical warning is logged on startup when demo mode is active.

3. **Cryptographic Hash Chain & Monotonic Sequence**:
   - Genesis event links to `GENESIS_HASH` (`"0" * 64`).
   - Each event computes `event_hash = SHA256(canonical_payload + previous_event_hash)` with strict alphabetical canonical JSON serialization including `tenant_id`.
   - Sequence allocation is strictly monotonic per tenant (`sequence = max(sequence) + 1`).
   - Verification endpoint `GET /api/v1/audit/verify` and `POST /api/v1/audit/verify` walks the entire chain from genesis to the latest record, verifying monotonicity, link hashes, and payload digests, returning `valid`, `event_count`, `broken_at_sequence`, and `violations`.

4. **Startup Integrity Verification**:
   - On server boot, `lifespan` automatically executes `startup_integrity_check()` across all tenant chains in persistent storage.
   - Any break in the sequence, linkage, or payload triggers a `CRITICAL` log and marks `app.state.audit_compromised = True` without crashing the process, allowing forensic recovery.

5. **Tenant Scoping & Actor Identity**:
   - `GET /api/v1/audit/events` is strictly scoped: `WHERE tenant_id = ?`.
   - Cross-tenant queries are blocked with HTTP 403 Forbidden unless caller possesses `admin` or `system` role.
   - `actor` identity is bound from the authenticated caller's identity (or `"local-user"` / `"nexusai-agent"`), completely ignoring client-supplied request bodies.

## Alternatives Considered
- **In-Memory Ledger with Periodic Disk Snapshots**: Rejected because unsaved audit events between snapshot intervals would be irrevocably lost during sudden crashes, violating compliance and non-repudiation requirements.
- **External Dedicated Append-Only Blockchain / Transparency Log (e.g., Sigstore/Rekor)**: Considered for enterprise multi-node clusters, but introduces external infrastructure dependencies unsuited for standalone dev or single-node production. The current SQLite architecture provides identical cryptographic tamper evidence locally while remaining zero-dependency.

## Consequences
### Positive
- **Guaranteed Durability**: Process restarts, crashes, and reloads preserve the entire historical audit log.
- **Strict Tamper-Evidence**: Any offline modification, event deletion, or reordering is immediately detected at boot or via `/verify`.
- **Production Hardening**: Accidental or malicious corruption via `/tamper` or `/reset` is blocked in production environments.
- **Multi-Tenant Confidentiality**: Audit ledgers are completely partitioned by tenant at the database and API query levels.

### Negative
- Synchronous write-behind adds a small disk I/O latency (< 0.5ms per event), well within the systemic 2.0ms pipeline overhead budget.
- Storage disk space grows monotonically over long runs; log rotation / archiving policies will be addressed in future enterprise milestones.

## Validation Criteria
- Unit tests (`tests/unit/infrastructure/persistence/test_sqlite_audit_store.py`) verify sequence monotonicity, restart persistence across separate store instances, tenant isolation, zero UPDATE/DELETE statements, and startup integrity checks.
- Integration tests (`tests/integration/test_audit_durability.py`) verify production 403 guards on tamper/reset, demo mode isolation, restart durability via API, tenant query isolation, and authenticated actor population.
- Master quality gates pass: Ruff linter clean, Black/isort formatted, MyPy strict clean, Architecture tests score 100/100.

## Review Phase
Quarterly review cycle, scheduled for Q4 2026.
