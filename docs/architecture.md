# 🏛️ NexusAI Agent Runtime — Architecture Specification

> **Platform Architecture Reference Document**  
> **Target Python Engine**: Python 3.12+ | Clean Architecture | Zero Circular Dependencies  

---

## 1. Clean Architecture Layers

NexusAI adheres to strict unidirectional Clean Architecture dependency rules:

```mermaid
graph TD
    Domain["1. Pure Domain Layer (src/nexusai/brain/domain/)\n- AgentGoal, PlanGraph, WorldState, ExecutionFailure"]
    Planner["2. Planner Pipeline Layer (src/nexusai/brain/planner/)\n- ExecutionPlanner, PlanValidator, PlanRepairEngine"]
    Runtime["3. Runtime Policy Layer (src/nexusai/brain/runtime/)\n- ExecutionPolicy, CircuitBreaker, ResourceManager"]
    Ports["4. Ports & Adapters Layer (src/nexusai/brain/ports/)\n- ToolCapabilityRegistry, RuntimeCapabilityDiscovery"]
    Memory["5. Memory Intelligence Engine (src/nexusai/brain/memory/)\n- MemoryIndexer, Ranker, ConflictResolver, ContextAssembler"]
    Events["6. Event Bus Infrastructure (src/nexusai/brain/events/)\n- AgentEventBus & Typed Domain Events"]
    Eval["7. Strategy Evaluation & Learning (src/nexusai/brain/eval/)\n- DecisionDataset, OfflineEvaluator, StrategyTrainer"]

    Planner --> Domain
    Runtime --> Domain
    Ports --> Domain
    Memory --> Domain
    Events --> Domain
    Eval --> Domain
    Runtime --> Planner
```

---

## 2. Planner Pipeline Architecture

The planner processes goals through a 5-stage decoupled pipeline, transforming high-level descriptions into a Directed Acyclic Graph (`PlanGraph`).

```mermaid
graph LR
    Goal["PlanningGoal"] --> Analyzer["GoalAnalyzer"]
    Analyzer --> Decomposer["TaskDecomposer"]
    Decomposer --> Resolver["DependencyResolver"]
    Resolver --> Ranker["ActionRanker"]
    Ranker --> ExecutionPlanner["ExecutionPlanner"]
    ExecutionPlanner --> PlanGraph["PlanGraph (DAG) & DecisionTrace"]
```

---

## 3. Memory Intelligence Pipeline

Memory context processing executes across 5 sequential transformations to maximize relevance and eliminate redundant context:

```mermaid
graph LR
    RawStore["Raw Observation / Session Store"] --> Indexer["MemoryIndexer\n(WORKING, EPISODIC, SEMANTIC, PROCEDURAL)"]
    Indexer --> Retriever["MemoryRetriever\n(Query & Importance Filter)"]
    Retriever --> Ranker["MemoryRanker\n(Relevance + Recency Decay + Confidence)"]
    Ranker --> Resolver["MemoryConflictResolver\n(Deduplication & Fact Certainty)"]
    Resolver --> Compressor["DeduplicatingClusterCompressor\n(Token Budget Compression)"]
    Compressor --> Assembler["ContextAssembler\n(Final Prompt Summary Payload)"]
```

---

## 4. Expectation Reflection & Plan Repair Pipeline

When a tool fails during execution, the `ReflectionEngine` diagnoses the root cause and `PlanRepairEngine` dynamically re-patches the DAG graph without aborting execution:

```mermaid
graph TD
    ToolFailure["ExecutionFailure\n(TIMEOUT, ERROR, PERMISSION_DENIED)"] --> Reflection["ReflectionEngine\n(Expectation-Outcome Gap Analysis)"]
    Reflection --> Diagnostic["ReflectionResult\n(Root Cause & Repair Suggestion)"]
    Diagnostic --> RepairEngine["PlanRepairEngine\n(DAG Mutation & Node Patching)"]
    RepairEngine --> PatchedGraph["Patched PlanGraph DAG"]
```

---

## 5. Runtime Execution & Policy Pipeline

The `PlanGraphExecutionEngine` executes DAG steps while enforcing runtime sandboxing policies and circuit breakers:

```mermaid
graph TD
    PlanGraph["PlanGraph (DAG)"] --> Validator["PlanValidator\n(Cycle Detection & Budget Verification)"]
    Validator --> Scheduler["Parallel ExecutionScheduler\n(Worker Pool & Ready Queue)"]
    Scheduler --> Policy["ExecutionPolicy & CircuitBreaker"]
    Policy --> ToolExecution["IToolPort Execution"]
    ToolExecution --> Telemetry["TraceCollector Spans & Metrics"]
```

---

## 6. Event-Driven Architecture (`AgentEventBus`)

Components publish typed domain events across the `AgentEventBus` to maintain complete decoupling:

```mermaid
graph TD
    Publisher["Runtime Engine / Planner"] --> EventBus["AgentEventBus"]
    EventBus --> Listener1["PlannerFinishedEvent Subscriber"]
    EventBus --> Listener2["ExecutionFinishedEvent Subscriber"]
    EventBus --> Listener3["ToolFailedEvent Subscriber"]
    EventBus --> Listener4["MemoryUpdatedEvent Subscriber"]
    EventBus --> Listener5["DecisionRecordedEvent Subscriber"]
```

---

## 7. Dynamic Capability Discovery

Tool capabilities are dynamically advertised and resolved at runtime:

```mermaid
graph LR
    MCP["MCP Server / Tool Provider"] --> Discovery["RuntimeCapabilityDiscovery\n(CapabilityAdvertisement)"]
    Discovery --> GraphBuilder["DynamicCapabilityGraphBuilder"]
    GraphBuilder --> CapabilityGraph["Ephemeral CapabilityGraph"]
```

---

## 8. Parallel Execution Scheduler

The `ExecutionScheduler` uses an asynchronous worker pool and dependency counter to run independent DAG branches concurrently:

```mermaid
graph TD
    NodeA["Root Step A"] --> Queue["Ready Queue"]
    Queue --> Worker1["Worker Task 1 (Step B)"]
    Queue --> Worker2["Worker Task 2 (Step C)"]
    Worker1 --> Join["Dependency Decrement & Merge Node D"]
    Worker2 --> Join
```

---

## 9. Closed-Loop Strategy Learning

The learning loop accumulates execution trajectories in `DecisionDataset` and automatically tunes scoring weights:

```mermaid
graph LR
    Execution["DecisionTrace Logs"] --> Dataset["DecisionDataset Entry Log"]
    Dataset --> Evaluator["OfflineEvaluator\n(Win Rate, Latency, Scalar Reward)"]
    Evaluator --> Trainer["StrategyTrainer"]
    Trainer --> TunedWeights["Updated PlannerWeights\n(Tuned Utility Scoring)"]
```
