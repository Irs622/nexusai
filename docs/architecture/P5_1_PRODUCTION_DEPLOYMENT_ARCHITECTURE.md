# P5-1 Architectural Design Specification: Production Deployment Architecture

**Status**: **APPROVED SPECIFICATION**  
**Milestone**: P5-1 Production Deployment Architecture Definition  
**Target Architectural Horizon**: NexusAI Phase 5 Production System  

---

## 1. Architectural Objective & Core Security Non-Regression Invariant

The primary objective of P5-1 is to define the authoritative production deployment architecture for NexusAI, transitioning the runtime from a single-host/multi-process SQLite baseline (Phase 4) to a multi-host, distributed, production-grade cloud deployment topology.

```text
===================================================================================
                   P5 NON-REGRESSION SECURITY INVARIANT
   "Distributed infrastructure MAY change persistence locations and coordination
  mechanisms, BUT IT MUST NEVER ALTER OR CREATE EXECUTION AUTHORITY OWNERSHIP."
===================================================================================
```

### Authoritative Execution Chain (Immutable):

```text
                               AUTHORITATIVE CORE
                                       │
User Request ──► Session Binding ──► PlanGraph ──► ActionBinding Digest Lock
                                       │
                                       ▼
Risk Evaluator ──► Human Approval (IHumanApprovalPort) ──► Governance (IGovernancePort)
                                       │
                                       ▼
                     Distributed Execution Coordinator (IExecutionCoordinator)
                                       │
                           Lease + Monotonic Fencing Token
                                       │
                                       ▼
                               ExecutionEngine
                                       │
                                       ▼
                             IToolPort (Real Tools)
```

**Critical Boundary Directive**: Worker leases, fencing tokens, PostgreSQL locks, or Redis key-value records **MUST NEVER** be interpreted as execution authorization. They remain purely operational concurrency mechanisms subordinate to the Authoritative Core.

---

## 2. Dependency-Driven Phase 5 Progression

```text
P5-1 Production Deployment Architecture Definition
        │
        ├──► P5-2 Distributed Execution Coordination (PostgreSQL / Redis with Fencing)
        │          │
        │          └──► P5-3 Durable Distributed Persistence (PostgreSQL Journal / Audit / Approval)
        │
        ├──► P5-4 Secrets & Credential Management (Vault / KMS Integration)
        │
        └──► P5-5 Tool Execution Sandbox & Process Isolation (gRPC Container Sandbox)
                    │
                    ▼
             P5-6 Disaster Recovery & Automated Snapshots
                    │
                    ▼
             P5-7 Production Observability & OpenTelemetry / Prometheus Exporters
                    │
                    ▼
             P5-8 Kubernetes Helm Deployment & Pod Security Standards
                    │
                    ▼
             P5-9 Multi-Node Cluster Verification & Adversarial Chaos Tests
                    │
                    ▼
             P5-FINAL Production Certification Gate
```

---

## 3. Production Deployment Topologies & Topology Matrix

NexusAI Phase 5 supports two explicitly defined, security-bounded deployment topologies:

```text
TOPOLOGY 1: SINGLE-HOST / MULTI-PROCESS WAL (Phase 4 Baseline)
┌─────────────────────────────────────────────────────────────────┐
│ Host Machine / Single VM / Worker Container                     │
│ ┌──────────────────────┐  ┌───────────────────────────────────┐ │
│ │ Worker Process 1     │  │ Worker Process 2                  │ │
│ └──────────┬───────────┘  └───────────────┬───────────────────┘ │
│            │                              │                     │
│            ▼                              ▼                     │
│   Shared POSIX Filesystem (SQLite WAL Mode: Busy Timeout 10s)   │
└─────────────────────────────────────────────────────────────────┘

TOPOLOGY 2: MULTI-HOST CLUSTER DEPLOYMENT (Phase 5 Horizon)
┌─────────────────────────┐  ┌─────────────────────────┐
│ Kubernetes Pod / Node 1 │  │ Kubernetes Pod / Node 2 │
│ ┌─────────────────────┐ │  │ ┌─────────────────────┐ │
│ │ Worker Instance A   │ │  │ │ Worker Instance B   │ │
│ └──────────┬──────────┘ │  │ └──────────┬──────────┘ │
└────────────┼────────────┘  └────────────┼────────────┘
             │                            │
             ▼                            ▼
┌─────────────────────────────────────────────────────────────────┐
│ Distributed Coordination Layer (PostgreSQL CAS / Redis Lease)    │
│  - Time-bounded Leases & Monotonic Fencing Tokens               │
│  - Strict Compare-And-Set (CAS) Isolation                        │
└─────────────────────────────────────────────────────────────────┘
```

### Deployment Topology Comparison Matrix:

| Feature / Property | Topology 1: Single-Host POSIX WAL | Topology 2: Distributed Multi-Host Cluster |
| :--- | :--- | :--- |
| **Primary Persistence** | Local SQLite (`journal_mode=WAL`) | PostgreSQL 16+ (Primary / Replica) |
| **Lease Coordination** | `SQLiteExecutionCoordinator` (CAS) | `PostgresExecutionCoordinator` / `RedisExecutionCoordinator` |
| **Network Boundary** | Host Local / IPC | TLS 1.3 / mTLS Subnet Boundary |
| **Fencing Token Mechanism** | Atomic SQL Counter (`MAX + 1`) | Atomic DB Sequence / Redis Lua Monotonic Increment |
| **Audit Storage** | `SQLiteAuditStore` (Local SHA-256 Chain)| `PostgresAuditStore` (Durable Append-Only Hash Chain) |
| **Secret Management** | Environment Variables / `.env` | HashiCorp Vault / Cloud KMS Dynamic Secret Engine |
| **Target Scale** | Up to 50 concurrent worker processes | Scalable to multi-node Kubernetes worker pods |

---

## 4. Technology Selection Rationale: PostgreSQL & Redis

### 1. Primary Distributed Storage & Coordination: PostgreSQL 16+
- **Role**: Primary authoritative store for `IApprovalStore`, `IExecutionJournal`, `IAuditStore`, and `IExecutionCoordinator`.
- **Consistency Semantics**: Strong Serializability / Read Committed with explicit `SELECT ... FOR UPDATE` row-level locks and Compare-And-Set (CAS) updates.
- **Fencing Token Mechanism**: Atomic DB `SEQUENCE` objects providing 100% strictly increasing 64-bit monotonically increasing integers across all nodes.
- **Why Not SQLite for Multi-Node?**: SQLite WAL mode requires POSIX shared memory locks (`.shm`) on a single filesystem; network filesystems (NFS/SMB) introduce locking bugs causing database corruption during multi-node writes.

### 2. High-Throughput Coordination Option: Redis Key-Value Store
- **Role**: Secondary optional high-performance lease coordinator (`RedisExecutionCoordinator`).
- **Consistency Semantics**: Time-bounded key expiration with atomic Lua scripting (`evalsha`) performing Compare-And-Set lease renewals and fencing token generation.
- **Fencing Token Mechanism**: `INCRBY` atomic sequence.
- **Failure Classification**: If Redis partition occurs, leases expire automatically via TTL; workers fail closed and must re-evaluate security gates upon recovery.

---

## 5. Network Trust, Secret Boundaries & Failure Domains

```text
┌─────────────────────────────────────────────────────────────────────────────────┐
│ UNTRUSTED ZONE                                                                  │
│ External User Request / Web UI / Webhook Entrypoint                             │
└──────────────────────────────────────┬──────────────────────────────────────────┘
                                       │ HTTPS / TLS 1.3
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│ DMZ / FACADE ZONE                                                               │
│ BrainRuntimeFacade ──► Auth Token Verification ──► Session Isolation Boundary   │
└──────────────────────────────────────┬──────────────────────────────────────────┘
                                       │ Internal Network Call
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│ AUTHORITATIVE CONTROL PLANE (KUBERNETES PODS)                                   │
│  - ExecutionPlanner                                                             │
│  - ToolRegistry                                                                 │
│  - HumanApprovalEngine (IApprovalStore)                                         │
│  - GovernanceEngine (IGovernancePort)                                           │
│  - CrashRecoveryManager                                                         │
└──────────────────┬───────────────────────────────────────────┬──────────────────┘
                   │ mTLS / TLS 1.3                            │ Dynamic KMS
                   ▼                                           ▼
┌──────────────────────────────────────┐     ┌────────────────────────────────────┐
│ DATA & COORDINATION ZONE             │     │ SECRETS ZONE                       │
│ PostgreSQL 16+ / Redis Cluster       │     │ HashiCorp Vault / Cloud KMS        │
└──────────────────────────────────────┘     └────────────────────────────────────┘
```

### Security & Secret Sanitization Boundaries:
1. **Zero Secret Persistence**: API keys, bearer tokens, passwords, and private keys **NEVER** enter PostgreSQL database tables or audit event logs (`sanitize_secrets_recursive()`).
2. **Dynamic KMS Fetching**: Real tool credentials (e.g. OpenAI API key, S3 access tokens) are fetched dynamically at runtime via HashiCorp Vault / KMS adapters and kept strictly in volatile memory.

---

## 6. Migration Strategy from Phase 4 SQLite Baseline

The transition from Phase 4 SQLite to Phase 5 Distributed Infrastructure follows an incremental, interface-preserving abstraction strategy:

```text
Phase 4 Interface Contracts (Immutable):
  - IApprovalStore
  - IExecutionJournal
  - IExecutionCoordinator
  - IAuditStore

Phase 5 Implementation Swap:
  SQLiteApprovalStore        ──► PostgresApprovalStore
  SQLiteExecutionJournal      ──► PostgresExecutionJournal
  SQLiteExecutionCoordinator  ──► PostgresExecutionCoordinator / RedisExecutionCoordinator
  SQLiteAuditStore           ──► PostgresAuditStore
```

Because Phase 4 established clear protocol interfaces under `src/nexusai/brain/ports/`, swapping the infrastructure persistence layer requires zero modifications to the Authoritative Core domain logic!

---

## 7. Phase 4 Security Invariants Compliance Checklist for Phase 5

Every Phase 5 milestone MUST verify that the 168 baseline security invariants established in Phase 4 remain 100% active:

1. ✅ **Single Execution Ownership**: Exactly 1 worker lease active per execution ID.
2. ✅ **Monotonic Fencing Tokens**: Stale worker token execution attempts fail closed (`call_count == 0`).
3. ✅ **Single-Use Approval Grants**: Approval grants cannot be re-consumed or resurrected across processes or nodes.
4. ✅ **Ambiguous Side-Effect Safeguard**: Crashed non-idempotent tool executions fail closed with status `ABANDONED`.
5. ✅ **Tamper-Evident Audit Chains**: Audit stores enforce SHA-256 hash chaining and sequence verification.
6. ✅ **Secret Redaction**: Credentials redacted before storage persistence.

---

## 8. Summary & Transition Verdict

The **P5-1 Production Deployment Architecture Definition** is **COMPLETE AND APPROVED**. 

We are ready to proceed directly to **P5-2: Distributed Execution Coordination with Strong Consistency and Fencing** (implementing `PostgresExecutionCoordinator` / `RedisExecutionCoordinator`).
