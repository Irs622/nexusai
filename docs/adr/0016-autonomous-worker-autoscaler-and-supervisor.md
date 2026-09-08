# ADR-0016: Autonomous Worker Auto-Scaler & Heartbeat Supervisor

- **Status**: Approved
- **Date**: 2026-09-02
- **Author**: Core AI Team (`irsalshydiq <ichalprov@gmail.com>`)
- **Review Phase**: Phase 7 / Level 4 Milestone

---

## 1. Context

In ADR-0014, NexusAI established the distributed execution foundation (`nexusai.infrastructure.distributed`), introducing worker node abstractions (`WorkerNode`), load routing (`DistributedWorkerPool`), and concurrent PlanGraph DAG branch execution (`DistributedExecutionScheduler`) coordinated via `IExecutionCoordinator` leases and fencing tokens.

However, the initial worker cluster implementation was static:
1. **Lack of Dynamic Dead Node Detection**: If a worker node crashed, encountered network partitions, or hung, its status in the pool was not automatically flagged as dead (silent failure), leading the scheduler to route tasks to unreachable nodes.
2. **Absence of Self-Healing**: There was no reconciliation mechanism to restore nodes to `ONLINE` status once their services recovered and ping latency stabilized.
3. **Static Capacity (Zero Elasticity)**: The number of active worker nodes in the pool could not dynamically adjust to DAG task queue backlog or cluster utilization, risking head-of-line blocking during traffic spikes or resource waste during quiet periods.

---

## 2. Decision

We decided to implement an **Autonomous Worker Auto-Scaler & Heartbeat Supervisor** within `nexusai.infrastructure.distributed`:

1. **`WorkerHeartbeatSupervisor` (`supervisor.py`)**:
   - Executes an asynchronous background supervision loop at configured periodic intervals (`check_interval_seconds`).
   - Dispatches health pings (`node.ping()`) and tracks round-trip latency and last-seen timestamps.
   - **Dead Node Eviction**: When a node fails to respond for $N$ consecutive checks (`max_consecutive_failures`, default 3), the supervisor transitions its status to `OFFLINE`, evicts it from the active candidate routing pool, and fires the `on_node_evicted` callback.
   - **Auto-Recovery**: When an `OFFLINE` or `DRAINING` node consistently succeeds on health pings for `recovery_threshold` consecutive rounds (default 2), the supervisor automatically restores it to `ONLINE` status and triggers `on_node_recovered`.

2. **`WorkerAutoScaler` (`autoscaler.py`)**:
   - Calculates aggregate cluster load metrics in real-time (`ClusterMetrics`): active capacity utilization $\frac{\sum \text{active\_tasks}}{\sum \text{capacity}}$ and pending task backlog size.
   - **Scale-Out**: When utilization $\ge 80\%$ or backlog queue size $> 0$, automatically instantiates new worker nodes (via `node_factory`, up to `max_nodes`).
   - **Scale-In**: When backlog is empty and utilization $\le 20\%$ after an established cooldown period (default 5s), performs graceful draining and unregisters idle dynamic nodes (preserving at least `min_nodes`).
   - **Anti-Thrashing Guard**: Enforces `cooldown_seconds` to eliminate thrashing oscillations between rapid scale-out and scale-in events.

3. **`ClusterOrchestrator` (`cluster_manager.py`)**:
   - Acts as the unified facade combining `DistributedWorkerPool`, `WorkerHeartbeatSupervisor`, and `WorkerAutoScaler`.
   - Manages the start/stop lifecycle of all cluster background tasks and exports status snapshots for Web OS telemetry and Server-Sent Events (SSE).

---

## 3. Alternatives Considered

1. **Relying Exclusively on Kubernetes HPA (Horizontal Pod Autoscaler)**:
   - *Rejected*: Kubernetes HPA is too slow for sub-second DAG task fluctuations (operates on 15–30 second scraping intervals) and cannot govern in-process worker routing or local developer environments.
2. **Reactive Scheduling-Time Polling Without Background Supervision**:
   - *Rejected*: Incurs unacceptable scheduling overhead on the critical DAG dispatch path and fails to detect dead nodes during idle periods.

---

## 4. Consequences

### Positive Consequences
- **Autonomous Self-Healing**: The cluster isolates unhealthy or unresponsive nodes automatically without human operator intervention.
- **Rapid Elasticity**: Dynamically absorbs bursty DAG workloads and frees compute resources during quiet periods.
- **Auditable Telemetry**: All scaling decisions are permanently recorded in structured `ScalingEvent` logs (`timestamp`, `direction`, `reason`, `nodes_before`, `nodes_after`).
- **Zero Thrashing**: Cooldown guards guarantee stable node sizing.

### Negative Consequences
- Introduces minimal CPU and network overhead for periodic node pings (benchmarked at $< 0.1\text{ms}$ per round).

---

## 5. Validation Criteria

1. **Heartbeat & Eviction Verification**:
   - A node failing $3\times$ consecutive pings transitions to `OFFLINE` and sets `is_evicted = True`.
2. **Auto-Recovery Verification**:
   - An offline node responding with 2 consecutive successful pings automatically transitions to `ONLINE`.
3. **Auto-Scaling Elasticity Verification**:
   - Backlog spikes trigger `SCALE_OUT` up to `max_nodes`.
   - Idle conditions trigger `SCALE_IN` down to `min_nodes` while observing cooldown limits.
4. **Clean Concurrency & Zero Leaked Tasks**:
   - `ClusterOrchestrator.stop()` cleanly terminates all background tasks without leaving uncollected asyncio tasks.

---

## 6. Review Phase

- Milestone: Phase 7 / Level 4 Production Hardening
- Target Release: v1.0.0-rc1 / v1.0.0
