# 12. Modular Planner, Dynamic Capability Discovery & Memory Intelligence Architecture

- **Status**: Approved
- **Deciders**: Core Architecture Team, OSPO Maintainer
- **Date**: 2026-08-07

---

## Context

As NexusAI evolved from an LLM invocation framework into an Agent Operating System, the monolithic `Planner` and naive `VectorSearch` models became major technical bottlenecks:
1. Hardcoded tool checks in planners violated Dependency Inversion.
2. Sequential step lists prevented parallel execution of independent tasks.
3. Memory retrieval suffered from context redundancy and fact contradiction.
4. Tool failures caused complete execution aborts without diagnostic reflection.

---

## Decision

We adopt a modular, stage-decoupled architecture across 5 key domain subsystems:

1. **Modular DAG Planner (`PlanGraph`)**:
   `GoalAnalyzer` $\rightarrow$ `TaskDecomposer` $\rightarrow$ `DependencyResolver` $\rightarrow$ `ActionRanker` $\rightarrow$ `ExecutionPlanner` producing `PlanGraph` DAGs.
2. **Dynamic Capability Discovery**:
   Planner requests capabilities via `CapabilityGraph`, resolved dynamically at runtime by `RuntimeCapabilityDiscovery` and `DynamicCapabilityGraphBuilder`.
3. **Multi-Tier Memory Intelligence Engine**:
   5-stage transformation (`MemoryIndexer` $\rightarrow$ `MemoryRetriever` $\rightarrow$ `MemoryRanker` $\rightarrow$ `MemoryConflictResolver` $\rightarrow$ `ContextCompressor` $\rightarrow$ `ContextAssembler`).
4. **Pre-Execution Validation & Sandboxing**:
   `PlanValidator` verifies DFS cycle detection and budget limits; `ExecutionPolicy` & `CircuitBreaker` prevent cascading failures.
5. **Expectation Reflection & Plan Repair**:
   `ReflectionEngine` assesses expectation-outcome gaps; `PlanRepairEngine` dynamically patches DAG nodes without full restart.

---

## Consequences

### Positive
- Zero hardcoded tool references in planning logic.
- Independent DAG branches execute concurrently via `ExecutionScheduler`.
- Contradictory memory facts are resolved deterministically by freshness and certainty.
- OpenTelemetry observability spans capture hierarchical latency breakdowns.

### Negative
- Minor increase in domain dataclass count (`PlanningContext`, `WorldState`, `PlanGraph`).
