# NexusAI Disaster Recovery Architecture & Operator Guide

```text
===================================================================================
                   P5-6 DISASTER RECOVERY SECURITY INVARIANT
   "NO DATABASE RESTORE, SNAPSHOT RESTORE, FAILOVER, BACKUP REPLAY, OR DISASTER
      RECOVERY PROCEDURE MAY CREATE OR RESURRECT EXECUTION AUTHORITY."
===================================================================================
```

## 1. Architectural Overview

The NexusAI Disaster Recovery Subsystem manages PostgreSQL automated snapshots, point-in-time recovery metadata, recovery epoch generation, lease invalidation, and audit chain verification.

```text
Backup Selection ──► Integrity Check (SHA-256) ──► Database Restore
                                                        │
                                                        ▼
System Ready ◄── Audit Chain Check ◄── Lease Invalidation & Epoch Increment (epoch += 1)
```

---

## 2. Recovery Epoch & Fencing Invalidation

After disaster recovery:
1. **Recovery Epoch Increment**: The system increments `recovery_epoch` (e.g. $1 \rightarrow 2$).
2. **Lease Invalidation**: All leases from previous epochs become immediately invalid.
3. **Stale Worker Rejection**: Any worker process submitting fencing tokens under an older recovery epoch is rejected with `FencingTokenError` or `StaleWorkerError`.

---

## 3. RPO / RTO Target Bounds

- **Recovery Point Objective (RPO)**: **5 minutes** (Automated snapshot interval).
- **Recovery Time Objective (RTO)**: **15 minutes** (Database restore, schema validation, lease invalidation, audit chain verification).
