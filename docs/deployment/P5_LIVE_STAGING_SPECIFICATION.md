# P5-LIVE: Staging Validation Specification & Real Side-Effect Harness

```text
===================================================================================
                   P5-LIVE STAGING SAFETY INVARIANT
   "NO TEST HARNESS OR EVIDENCE COLLECTOR MAY BECOME EXECUTION AUTHORITY.
  ALL EVIDENCE MUST DERIVE FROM OBSERVABLE AUTHORITATIVE EXTERNAL STATE."
===================================================================================
```

## 1. Scope & Certification Objective

P5-LIVE provides the operational specification and test harness required to transition NexusAI from **Level 3 (Production-Like Verified)** to **Level 4 (Production Certified)**.

Layer E/F certification requires real evidence collected from a preflight-validated staging environment under real fault injections (network partitions, node crashes, pod evictions, disaster recovery epoch transitions).

---

## 2. Staging Architecture & Preflight Gate

```text
Preflight Check ──► Dry-Run Validation ──► Staging Execution (Fault Injection)
       │                                            │
       ▼                                            ▼
Production Endpoint                              PostgreSQL State +
Denial & Digest Check                          Real Atomic Sink Counter
                                                    │
                                                    ▼
                                          Evidence Collector
                                           (SHA-256 Hash Chain)
```

### Preflight Verification Requirements (`--mode preflight`)
- Cluster Identity: `expected == actual` (`nexusai-staging`)
- Namespace: `expected == actual` (`nexusai-staging`)
- Database / Redis / Vault / OTEL Endpoints: Verified `STAGING` environment tags.
- Production Endpoints: Explicitly **DENIED** (`0` production hosts detected).
- Image Digests: Pinned against allowlisted SHA-256 digests.

---

## 3. Correlation Identity & Real Side-Effect Evidence Model

Every staging execution carries a mandatory correlation identity:

```text
execution_id
attempt_id
idempotency_key
worker_id
fencing_token
recovery_epoch
scenario_id
timestamp
```

Authoritative side-effect truth is governed by PostgreSQL `UNIQUE(idempotency_key)` constraints and atomic database transaction commits.

- **Stale Worker Attempts**: `stale_worker_attempts > 0`
- **Stale Worker Real Side Effects**: `stale_worker_real_side_effects == 0`
- **Committed Real Side Effects**: `committed_side_effects <= 1`

---

## 4. 15 Adversarial Scenario Matrix & Execution Chains

### Failure Scenario Chain (`P5-LIVE-FAIL-01` to `P5-LIVE-FAIL-09`)
- `P5-LIVE-FAIL-01`: Active Worker Pod Crash (`SIGKILL`)
- `P5-LIVE-FAIL-02`: Worker Node Termination
- `P5-LIVE-FAIL-03`: Worker Pod Eviction
- `P5-LIVE-FAIL-04`: CNI Network Partition (Worker A partitioned from Coordinator)
- `P5-LIVE-FAIL-05`: Worker A Reconnect (Stale worker reconnection with token $N$)
- `P5-LIVE-FAIL-06`: PostgreSQL Primary Failover
- `P5-LIVE-FAIL-07`: Redis Coordinator Restart
- `P5-LIVE-FAIL-08`: Vault / KMS Service Interruption
- `P5-LIVE-FAIL-09`: OTEL Collector Outage

### Disaster Recovery Branch (`P5-LIVE-REC-10` to `P5-LIVE-REC-11`)
- `P5-LIVE-REC-10`: Disaster Recovery Point-in-Time Restore (`recovery_epoch += 1`)
- `P5-LIVE-REC-11`: Backup Checksum Tamper Quarantine (`RecoveryStatus.QUARANTINED`)

### Distributed Race Chain (`P5-LIVE-RACE-12` to `P5-LIVE-RACE-15`)
- `P5-LIVE-RACE-12`: Multi-Node Dual Lease Acquisition (Nodes A, B, C race)
- `P5-LIVE-RACE-13`: Lease Expiration & Takeover ($token_A = 1 \rightarrow token_B = 2$)
- `P5-LIVE-RACE-14`: Stale Node A Lease Renewal Attempt (Rejected)
- `P5-LIVE-RACE-15`: Stale Node A Lease Release Attempt (Rejected)

---

## 5. Hard Abort Controller Safety Rules

Execution halts immediately if:
1. `duplicate_real_side_effects > 0`
2. Unknown or stale fencing token accepted
3. `recovery_epoch` decreases
4. Production endpoint or database DSN detected
5. Unapproved cluster context or namespace detected
6. Evidence collector attempts to grant/manufacture execution authority

---

## 6. Binary Level-4 Certification Gates

Level 4 Production Certification is granted **IF AND ONLY IF** all of the following evaluate to `TRUE`:

```text
REAL_CLUSTER_VERIFIED == true
REAL_POSTGRES_VERIFIED == true
REAL_REDIS_VERIFIED == true
REAL_VAULT_KMS_VERIFIED == true
REAL_OTEL_VERIFIED == true
REAL_MULTI_NODE_VERIFIED == true
STALE_WORKER_REAL_SIDE_EFFECTS == 0
DUPLICATE_REAL_SIDE_EFFECTS == 0
RECOVERY_EPOCH_INVALIDATION_VERIFIED == true
NO_CRITICAL_FINDINGS == true
NO_HIGH_FINDINGS == true
ALL_REQUIRED_SCENARIOS_PASS == true
EVIDENCE_INTEGRITY_VERIFIED == true
```
