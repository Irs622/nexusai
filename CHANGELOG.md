# 📜 Changelog

All notable changes to **NexusAI** will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### 🚀 Phase 7 / Level 4: Built-in MCP Server Pack & Ecosystem Integration (ADR-0015)
- `feat(mcp)`: Implement native Python 3.12+ Built-in MCP Server Pack running over stdio JSON-RPC 2.0 out-of-the-box without requiring external `npm` or `uvx` dependencies.
  - `FilesystemMcpServer`: Secure sandboxed workspace operations (`read_file`, `write_file`, `list_directory`, `get_file_info`, `search_files`) with strict path traversal jail boundary enforcement.
  - `SqliteMcpServer`: Non-blocking async SQLite execution (`read_query`, `write_query`, `list_tables`, `describe_table`) with parameterized query support via `aiosqlite`.
  - `WebFetcherMcpServer`: Asynchronous web page content extraction (`fetch_url`) stripping script/style tags and generic HTTP requests (`http_request`) via `httpx`.
  - `McpServerBase`: Resilient stdio JSON-RPC 2.0 base framework handling initialization, ping, tool discovery, and tool call dispatching with standard output flushing and error isolation.
- `feat(mcp)`: Auto-resolve `python` / `python3` command to active `sys.executable` and propagate process exit/stderr errors instantly in `McpClient`.
- `feat(distributed)`: Implement `DistributedWorkerPool` and `DistributedExecutionScheduler` coordinating PlanGraph DAG branches across distributed worker nodes with monotonic fencing tokens (ADR-0014).
- `feat(web)`: Real-time Server-Sent Events (SSE) stream (`/api/events/stream`), REST MCP endpoints (`/api/mcp/servers`, ping, reload), and Cyber-Glassmorphism Web OS dashboard.
- `feat(distributed)`: Implement `WorkerHeartbeatSupervisor` for dead node eviction and auto-recovery, `WorkerAutoScaler` for queue-based dynamic scale-out/scale-in with anti-thrashing cooldown, and `ClusterOrchestrator` unified facade (ADR-0016).
- `feat(test)`: Continuous soak & endurance test harness (`tools/run_soak_test.py`) tracking zero memory leak curves, GC object retention, and latency drift.

---

## [0.7.0] - 2026-08-12

### 🚀 Phase 5: Production Deployment, Multi-Node Coordination & Governance
- `feat(coordination)`: Implement `PostgresExecutionCoordinator` and `RedisExecutionCoordinator` for multi-worker distributed lease coordination and monotonic fencing tokens.
- `feat(persistence)`: Implement durable PostgreSQL execution persistence, transaction boundaries, and SQLite migration pipeline.
- `feat(secrets)`: Implement HashiCorp Vault (`VaultCredentialProvider`) and AWS KMS (`KMSCredentialProvider`) credential management with automatic secret rotation.
- `feat(sandbox)`: Implement process and gRPC sandbox isolation with capability policies.
- `feat(dr)`: Implement disaster recovery, snapshot metadata, and epoch tracking.
- `feat(observability)`: Implement OpenTelemetry-compatible structured logging and Prometheus metric exporters.
- `feat(k8s)`: Implement Helm deployment manifests, non-root security contexts, read-only root filesystems, and image digest pinning support.

---

## [0.6.0] - 2026-08-07

### 🟢 Added — Phase 6: End-to-End Integration, Observability & Learning Loop
- `feat(telemetry)`: OpenTelemetry-compatible `ExecutionSpan` and `TraceCollector` capturing sub-operation timeline spans and aggregated latency breakdowns (`planner.plan`, `tool.execute`, `reflection.reflect`).
- `feat(runtime)`: Granular `ResourceManager` and `ResourceBudget` tracking CPU, RAM, token limits, concurrency worker ceilings, API cost ceilings, and raising `ResourceQuotaExceededError`.
- `feat(runtime)`: `AdaptiveBudgetAdaptation` dynamically scaling down concurrency and context depth when resource budgets run low.
- `feat(eval)`: Closed-loop `OfflineEvaluator` and `StrategyTrainer` automatically tuning `PlannerWeights` based on historical `DecisionDatasetEntry` outcomes and scalar rewards.
- `feat(memory)`: `DeduplicatingClusterCompressor` deduplicating exact/near-duplicate texts before token budget compression.

---

## [0.5.0] - 2026-08-07

### 🟢 Added — Phase 5: Modular Planner, Capability Discovery, Execution Policy & Memory Intelligence
- `feat(planner)`: Modular ExecutionPlanner pipeline stages (`GoalAnalyzer`, `TaskDecomposer`, `DependencyResolver`, `ActionRanker`, `ExecutionPlanner`) producing `PlanGraph` DAG plans.
- `feat(planner)`: Pre-execution `PlanValidator` verifying DFS cycle detection, dead-end nodes, unreachable steps, and budget bounds.
- `feat(planner)`: Parallel async `ExecutionScheduler` running independent DAG branches concurrently via worker queues.
- `feat(ports)`: Dynamic `RuntimeCapabilityDiscovery` and ephemeral `DynamicCapabilityGraphBuilder` decoupling planning from hardcoded tool names.
- `feat(runtime)`: `ExecutionPolicy` and `CircuitBreaker` sandboxing preventing cascading tool failures across `CLOSED`, `OPEN`, and `HALF_OPEN` states.
- `feat(planner)`: `PlanGraphExecutionEngine` executing DAG nodes sequentially or concurrently enforcing runtime policies.
- `feat(eval)`: `DecisionDataset` and `DecisionDatasetEntry` capturing execution decision trajectories for offline evaluation and RL training.
- `feat(memory)`: Multi-tier Memory Intelligence pipeline (`MemoryIndexer`, `MemoryRetriever`, `MemoryRanker` with exponential recency decay, `MemoryConflictResolver`, `ContextCompressor`, `ContextAssembler`, `MemoryPolicy`).
- `feat(domain)`: `WorldState` domain model encapsulating workspace path, environment variables, active MCP servers, and system resources.
- `feat(events)`: Publish-subscribe `AgentEventBus` and typed domain events (`PlannerFinishedEvent`, `ExecutionStartedEvent`, `ExecutionFinishedEvent`, `ToolFailedEvent`, `MemoryUpdatedEvent`, `DecisionRecordedEvent`).
- `feat(reflection)`: Diagnostic `ReflectionEngine` assessing expectation-outcome gaps and `PlanRepairEngine` dynamically patching `PlanGraph` DAG nodes.
- `feat(memory)`: `MemoryConsolidator` consolidating stale episodic memories into permanent semantic knowledge summaries.

---

## [0.4.0] - 2026-08-06

### 🟢 Added — Phase 4: Quality Engineering & Replay Infrastructure
- `feat(replay)`: Deterministic execution replay (`ReplayRecorder`, `ReplayRunner`, `ExecutionLog`, `ExecutionEvent`).
- `feat(state)`: Core and Extended state hash computation (`compute_core_state_hash`, `compute_extended_state_hash`).
- `feat(eval)`: Golden scenario corpus generation (`ScenarioCorpus`, `ScenarioRunner`, `AgentEvaluator`, `BenchmarkComparator`, `BenchmarkReportAggregator`).
- `feat(ci)`: Automated benchmark regression detection and CI quality gate.

---

## [0.3.0] - 2026-08-04

### 🟢 Added — Phase 3: Brain Runtime Core
- `feat(brain)`: Versioned domain contracts and runtime context infrastructure (`BrainSession`, `ExecutionContext`, `PromptBundle`, `ArtifactRegistry`).
- `feat(brain)`: Provider ExecutionPlan and Capability Negotiation Bridge (`RequiredCapabilities`, `ProviderSelector`).
- `feat(brain)`: Delta streaming execution, telemetry tracer, and Kernel Outbox transactional persistence.

---

## [0.2.0] - 2026-08-03

### 🟢 Added — Phase 2: Kernel Orchestration Engine & Quality Gate
- `feat(kernel)`: Deterministic boot, topological dependency resolution, state machine lifecycle coordination, and `KernelOrchestrator`.
- `feat(quality)`: Modular quality gate runners (`run_formatter.py`, `run_linter.py`, `run_typecheck.py`, `run_tests.py`, `run_quality_gate.py`).

---

## [0.1.0-alpha] - 2026-08-03

### 🟢 Added — Initial Alpha Release
- Core CQRS architecture (`CommandBus`, `QueryBus`, `EventBus`).
- Model-agnostic LLM provider interfaces (OpenAI, OpenRouter, Ollama, Gemini, Anthropic).
- Interactive CLI application (`nexusai chat`) and Web Dashboard.
- Security Guard and Risk Classifier (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`).
