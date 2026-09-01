# 14. Distributed Worker Node Scheduler & Cluster Execution

- **Status**: Approved
- **Deciders**: Core Architecture Team, Infrastructure Maintainer
- **Date**: 2026-09-01
- **Review Phase**: Phase 7 / Level 4 Milestone

---

## Context

As NexusAI attains Level 4 Production Certification, runtime execution workloads scale from single-process asynchronous task graphs to multi-node distributed compute clusters. Complex execution graphs (`PlanGraph`) often contain independent branches that can be executed in parallel across multiple worker nodes (in-process workers, isolated Docker containers, or remote HTTP/gRPC worker pods in Kubernetes).

Prior to this decision:
1. `ExecutionScheduler` was confined to a single Python asyncio event loop executing tasks locally in-process.
2. In the event of high compute load, process crashes, or worker evictions, tasks could not be dynamically re-routed or failed over across distinct physical nodes or containers.
3. While `IExecutionCoordinator` with distributed leasing and monotonic fencing tokens ($T_n$) was implemented in Phase 5, there was no high-level scheduler integrating dynamic cluster worker pools with lease acquisition, heartbeating, and automated failover.

---

## Decision

We implement a distributed worker node orchestration and scheduling subsystem under `nexusai.infrastructure.distributed`:

1. **Worker Node Abstraction (`WorkerNode`)**:
   - Represents an execution node with lifecycle status (`ONLINE`, `BUSY`, `DRAINING`, `OFFLINE`).
   - Tracks runtime operational metrics: active tasks, maximum concurrency, average latency, and error count.
   - Provides asynchronous execution dispatch and health check pinging.

2. **Distributed Worker Pool (`DistributedWorkerPool`)**:
   - Maintains a cluster pool of worker nodes.
   - Provides pluggable task routing strategies:
     - `LEAST_BUSY`: Routes execution requests to the healthy node with the lowest active task load.
     - `ROUND_ROBIN`: Cycles task distribution evenly across all healthy nodes.
     - `CAPABILITY_MATCH`: Matches requested tool capabilities or labels against worker node capabilities.
   - Manages graceful node draining (`drain_node()`) and dynamic registration/deregistration.

3. **Distributed Execution Scheduler (`DistributedExecutionScheduler`)**:
   - Extends DAG branch concurrency across the distributed cluster.
   - Concurrently processes nodes with in-degree == 0.
   - Acquires time-bounded `ExecutionLease` from `IExecutionCoordinator` with monotonic fencing tokens before delegating work to a selected `WorkerNode`.
   - Runs asynchronous lease renewal (heartbeat) during active execution.
   - Implements automated failover: if a worker node crashes or times out, the lease is recovered via `recover_expired_execution_lease()`, incrementing the fencing token ($T_{n} \rightarrow T_{n+1}$), and the task is rescheduled to a healthy standby worker without duplicate side effects.
   - Unlocks dependent child nodes upon verified completion.

---

## Alternatives Considered

1. **Relying Exclusively on Celery / Celery Beat**:
   - *Rejected*: Introduces heavy external dependencies (RabbitMQ/Celery brokers), breaks NexusAI's domain execution model, and lacks native integration with NexusAI's tamper-evident SHA-256 evidence chain and `IExecutionCoordinator` fencing tokens.
2. **Kubernetes Jobs Per Task Node**:
   - *Rejected*: Incurring pod spin-up latency (seconds to tens of seconds) per DAG node is unacceptable for low-latency agent reasoning pipelines ($< 2.0\text{ms}$ scheduling overhead target). A warm worker pool with HTTP/gRPC invocation is far superior.

---

## Consequences

### Positive
- Enables linear horizontal scalability across multi-node Kubernetes worker pools.
- Maintains strict zero-dual-authority guarantees via `IExecutionCoordinator` fencing tokens ($T_n$).
- Automated failover and circuit breaking prevent cluster-wide cascading failures.
- Clean separation: application domain `nexusai.brain` remains fully decoupled from concrete cluster transport.

### Negative
- Distributed network roundtrips introduce minor network latency compared to pure in-memory execution; mitigated by `LEAST_BUSY` routing and local worker affinity.

---

## Validation Criteria

1. Unit tests verify `WorkerNode` lifecycle, concurrency limiting, and metric collection.
2. Pool routing tests verify `LEAST_BUSY` and `ROUND_ROBIN` load balancing distributions.
3. Scheduler tests verify parallel DAG execution across multiple mock worker nodes.
4. Failover tests prove that when an active worker crashes, task is reassigned with a monotonically increased fencing token ($T_1 \rightarrow T_2$) and produces zero dual-execution side effects.
5. All architecture fitness tests pass with 0 DAG boundary violations.
