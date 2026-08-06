# Kernel Orchestration Engine (Phase 2.5)

## Overview

The **Kernel Orchestration Engine** provides deterministic, resilient lifecycle management, dependency ordering, background task execution, and system state snapshotting for all NexusAI OS subsystems.

## Core Components

```
                     ┌─────────────────────────────────────────┐
                     │           KernelOrchestrator            │
                     └────────────────────┬────────────────────┘
                                          │ (Facade)
          ┌─────────────────┬─────────────┼─────────────┬─────────────────┐
          │                 │             │             │                 │
┌─────────▼────────┐ ┌──────▼──────┐ ┌────▼────┐ ┌──────▼──────┐ ┌────────▼────────┐
│ ServiceRegistry  │ │  Dependency │ │Lifecycle│ │  Runtime    │ │ Background      │
│                  │ │    Graph    │ │Coordinator│Scheduler   │ │ WorkerManager   │
└──────────────────┘ └─────────────┘ └─────────┘ └─────────────┘ └─────────────────┘
```

1. **ServiceRegistry** (`nexusai.kernel.registry`)
   - Thread-safe service registration, lookup by ID, interface, tag, and status filters (`list_running()`, `list_failed()`).

2. **RuntimeDependencyGraph** (`nexusai.kernel.dependency_graph`)
   - Directed Acyclic Graph (DAG) manager providing Kahn's topological sort for startup order, reverse sort for shutdown order, cycle detection (`DependencyCycleError`), and post-bootstrap freezing (`is_frozen`).

3. **LifecycleCoordinator** (`nexusai.kernel.lifecycle`)
   - Manages state machine transitions (`UNINITIALIZED -> INITIALIZED -> STARTING -> RUNNING -> STOPPING -> STOPPED`).
   - Implements automated rollback (`ROLLING_BACK` state) on boot failure.

4. **RuntimeScheduler** (`nexusai.kernel.scheduler`)
   - Async scheduler for time-based periodic and one-shot scheduled tasks with exception isolation.

5. **BackgroundWorkerManager** (`nexusai.kernel.worker`)
   - Queue-based background worker manager for execution queues.

6. **SnapshotManager** (`nexusai.kernel.snapshot`)
   - Captures immutable `KernelSnapshot` records for system diagnostics, recovery, and audit trails.

7. **KernelOrchestrator** (`nexusai.kernel.orchestrator`)
   - Composition Root facade delegating to registry, coordinator, scheduler, worker manager, and snapshot manager.

## Failure Resilience Invariants

- **Boot Failure Rollback**: If a service fails to initialize or start during bootstrap, all previously started services are rolled back in reverse topological order (`ROLLING_BACK -> STOPPED`), ensuring no orphan running processes remain.
- **Restart After Failure**: The state machine allows fixing a failing service and re-executing `boot()`, restoring all services to `RUNNING`.
