---
status: accepted
date: 2026-09-12
decision-makers:
  - runtime-architect
  - core-team
consulted:
  - security-team
  - governance-team
informed:
  - contributors
---

# ADR 0034: Durable Execution Engine with Crash Recovery and Fencing Tokens

## Status
Accepted

## Context
Prior to this architectural enhancement, NexusAI DAG plan execution in the API layer relied on in-memory asynchronous tasks (`asyncio.create_task()`). This model introduced significant operational and distributed vulnerabilities:
1. **Volatile Process Fate**: An unhandled exception, SIGKILL, container eviction, or host reboot resulted in lost execution state with zero recovery, checkpointing, or resume capability.
2. **Disconnected Coordination**: While worker lease acquisition and monotonic fencing token concepts existed in `IExecutionCoordinator`, they were not integrated into the runtime execution engine loop.
3. **Unbounded Side Effects**: The runtime lacked classification of tool execution semantics (`ExecutionSemantics`), leading to ambiguous or dangerous retries on side-effecting operations like sending emails or posting webhooks.
4. **Architectural Pipeline Fragmentations**: Multiple execution routes existed (`WorkflowGraphEngine`, `PlanGraphExecutionEngine`, and direct coordinator loops), introducing inconsistency in governance, audit, and security validation.

Remediation requires a persistent execution state machine, step-level checkpointing & resume, worker lease fencing, configurable retry policies, durable cancellation surviving restart, explicit side-effect execution semantics on tools, and a crash recovery protocol.

## Decision
We implement an authoritative, persistent, fault-tolerant execution engine:

### 1. Persistent Execution State Machine
Executions transition through an immutable, validated lifecycle:
`CREATED` → `QUEUED` → `RUNNING` → `CHECKPOINT` → `SUCCEEDED` / `FAILED_RETRYABLE` / `FAILED_TERMINAL` / `CANCELLED` / `TIMED_OUT`.
- Every transition is persisted to SQLite (`execution_state_transitions` table) before side effects.
- Transitions are actor-attributed (`actor`, `worker_id`, `tenant_id`) and timestamped.
- Idempotent: re-applying an identical state transition is a no-op.
- Fencing token checked: stale workers holding obsolete tokens are rejected with `FencingTokenError`.

### 2. Checkpoint & Resume
For multi-step DAG executions:
- Each completed step writes an atomic checkpoint (`output_json`, status `COMPLETED`) to `node_executions`.
- Upon crash and subsequent recovery, `DurableExecutionEngine.resume_execution` loads existing checkpoints and executes only uncompleted steps (e.g. steps 1–3 completed before crash → only steps 4 and 5 execute).

### 3. Worker Leases & Monotonic Fencing Tokens
- Executions require a time-bounded lease acquired via `IExecutionCoordinator`.
- Leases assign monotonically increasing fencing tokens ($N \rightarrow N+1$).
- When an execution lease expires due to worker death, a failover worker reclaims ownership with a higher fencing token. Any subsequent write attempts by the zombie worker are rejected.

### 4. Configurable Retry Policy (`DurableRetryPolicy`)
- Retry configuration supports exponential, linear, or fixed backoff with jitter and configurable ceilings.
- Error taxonomy separates retryable failures (`TIMEOUT`, `TRANSIENT_FAILURE`, `NETWORK_ERROR`, `RATE_LIMITED`) from non-retryable failures (`PERMISSION_DENIED`, `INVALID_INPUT`, `AUTHENTICATION_ERROR`, `AUTHORIZATION_ERROR`, `GOVERNANCE_VIOLATION`).
- Non-retryable errors immediately trigger terminal failure (`FAILED_TERMINAL`).

### 5. Side-Effect Execution Semantics (`ExecutionSemantics`)
Tools declare their side-effect characteristics via `BaseTool.execution_semantics`:
- `IDEMPOTENT`: Safe to retry automatically with identical parameters.
- `DEDUPLICATED`: Internally deduplicates via client idempotency keys.
- `TRANSACTIONAL`: Supports rollback on failure.
- `AT_LEAST_ONCE`: Default safe baseline; may produce duplicate side effects. Retries on `HIGH` or `CRITICAL` risk tools strictly require explicit human approval (`ApprovalRequiredError`).
- Constraint: `execution_semantics` is declared on tool classes and is strictly immutable from client request bodies.
- Execution semantics and attempt counts are appended to `IAuditStore` events.

### 6. Durable Cancellation
- `POST /api/v1/executions/{id}/cancel` persists state `CANCELLED` and signals active tasks.
- Completed steps remain preserved; cancellation persists across restarts and prevents crash recovery re-execution.

### 7. Startup Crash Recovery Protocol (`CrashRecoveryProtocol`)
- Upon daemon startup, the recovery protocol scans the store for executions in `RUNNING`, `QUEUED`, `CHECKPOINT`, or `FAILED_RETRYABLE`.
- Stale executions with expired worker leases are reclaimed with higher fencing tokens.
- Executions with pending cancellations are finalized to `CANCELLED`.
- Executions exceeding maximum recovery retries are transitioned to `FAILED_TERMINAL`.

### 8. Pipeline Consolidation
- Legacy `WorkflowGraphEngine` is formally deprecated with `DeprecationWarning`.
- API DAG executions route through `DurableExecutionEngine.execute_dag(...)`.

## Alternatives Considered
- **Temporal / Cadence Workflow Engine**: Heavyweight external daemon dependencies; unsuitable for single-node embedded deployments.
- **Pure Celery / Redis Task Queue**: Lacks ACID state machine journaling and transactional SQLite WAL consistency.
- **In-Memory Volatile Tasks**: Original design; vulnerable to data loss and uncoordinated split-brain execution.

## Consequences
### Positive
- Zero task loss upon process termination or sudden power outage.
- Resumes multi-step DAG executions without repeating expensive or non-idempotent steps.
- Complete auditability and inspection via `GET /api/v1/executions/{id}`.
- Distributed mutual exclusion guaranteed by leases and fencing tokens.

### Negative / Trade-offs
- Slight persistence overhead (< 1.5ms per step) for SQLite WAL checkpointing and audit journaling.
- Requires explicit approval gate configuration for retrying high-risk `AT_LEAST_ONCE` tools.

## Validation Criteria
- `tests/unit/runtime/test_execution_engine.py`: 8/8 unit tests verifying state transitions, fencing rejection, retry backoff, approval gates, and cancellation.
- `tests/integration/test_crash_recovery.py`: 4/4 integration tests verifying multi-step DAG crash resume, lease reclaim, cancelled execution resilience, and approval retry paths.
- Master quality gates clean: Ruff, Black, isort, MyPy strict, Architecture fitness 100/100.
