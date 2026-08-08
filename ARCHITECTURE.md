# 🏛️ Architecture Documentation

The master architecture documentation for **NexusAI Agent Runtime** has been relocated to [`docs/architecture.md`](docs/architecture.md).

Please refer to [`docs/architecture.md`](docs/architecture.md) for detailed specifications on:

- Clean Architecture layers and dependency boundaries
- Planner Pipeline (`PlanGraph` DAG generation)
- Memory Intelligence Engine (Indexer, Retriever, Ranker, Conflict Resolver, Compressor, Assembler)
- Expectation Reflection & Plan Repair Pipeline
- Runtime Execution Engine & Policy Sandboxing (`CircuitBreaker`, `ResourceManager`)
- Publish-Subscribe `AgentEventBus`
- Dynamic Capability Discovery & Ephemeral Graph Construction
- Parallel Async `ExecutionScheduler`
- Closed-Loop Strategy Learning (`DecisionDataset`, `OfflineEvaluator`, `StrategyTrainer`)
