---
status: stable
audience:
  - architects
  - core-developers
  - contributors
owner:
  - core-team
applies_to:
  - architectural-decision-records
review_cycle: quarterly
last_reviewed: 2026-09-09
---

# 📜 Architectural Decision Records (ADRs) Index

This directory documents key architectural decisions made during the design, implementation, and hardening of the NexusAI AI Operating System.

---

## 📑 ADR Index

| ADR ID | Title | Status | Scope |
|---|---|---|---|
| [ADR 0001](0001-plugin-system.md) | Extensible Tool Plugin Architecture & Lifecycle Hooks | Accepted | Plugins |
| [ADR 0002](0002-memory-storage.md) | Dual-Tier Local Memory Architecture & SQLite Persistence | Accepted | Memory |
| [ADR 0003](0003-security-evaluator.md) | Command Security Guard & Risk Classification Model | Accepted | Security |
| [ADR 0004a](0004-immutable-agent-context.md) | Immutable AgentContext and Reducer Pattern | Accepted | Core State |
| [ADR 0004b](0004-provider-interface.md) | Model-Agnostic Provider Interface | Superseded by 0006 | Models |
| [ADR 0005](0005-reasoning-and-observation-architecture.md) | Pluggable ReasoningEngine and Immutable Observation Layer | Accepted | Brain |
| [ADR 0006](0006-provider-sdk.md) | Vendor-Agnostic Provider SDK Foundation & Architecture | Accepted | Provider SDK |
| [ADR 0007](0007-canonical-model-evolution.md) | Governance Principles for Canonical Model Evolution | Accepted | Provider SDK |
| [ADR 0008](0008-brain-runtime-architecture.md) | Stateless Brain Runtime Architecture & Execution Pipeline | Accepted | Brain Runtime |
| [ADR 0009](0009-agent-runtime-architecture.md) | Multi-Turn Agent Runtime & Decoupled Loop Orchestration Architecture | Accepted | Agent Runtime |
| [ADR 0010](0010-context-compaction-and-memory-retention.md) | Context Compaction and Memory Retention Architecture | Accepted | Context & Memory |
| [ADR 0011](0011-extensibility-and-extension-points.md) | Framework Extension Points and Plugin Boundaries | Accepted | Extensibility |
| [ADR 0012](0012-modular-planner-and-memory-pipeline.md) | Modular Planner, Dynamic Capability Discovery & Memory Intelligence Architecture | Accepted | Planner & Memory |
| [ADR 0013](0013-model-context-protocol-integration.md) | Model Context Protocol (MCP) Client & Tool Adapter Integration | Accepted | MCP Client |
| [ADR 0014](0014-distributed-worker-node-scheduler.md) | Distributed Worker Node Scheduler & Cluster Execution | Accepted | Distributed |
| [ADR 0015](0015-builtin-mcp-server-pack.md) | Built-in Model Context Protocol (MCP) Server Pack | Accepted | Built-in MCP |
| [ADR 0016](0016-autonomous-worker-autoscaler-and-supervisor.md) | Autonomous Worker Auto-Scaler & Heartbeat Supervisor | Accepted | Distributed & Elasticity |
| [ADR 0017](0017-multi-agent-collaboration-mesh.md) | Multi-Agent Collaboration Mesh (A2A Protocol & Mesh) | Accepted | Multi-Agent |
| [ADR 0018](0018-remote-mcp-sse-and-http-transport.md) | Remote Model Context Protocol (MCP) Server-Sent Events (SSE) & HTTP Streaming Transport | Accepted | Remote MCP |
| [ADR 0019](0019-postgresql-pgvector-and-qdrant-memory-adapters.md) | Distributed Semantic Memory Adapters: PostgreSQL pgvector & Qdrant | Accepted | Distributed Memory |
| [ADR 0020](0020-webhook-notification-gateway-for-human-approval.md) | Webhook Notification Gateway for Human-In-The-Loop Approvals | Accepted | Governance & Notifications |

---

## 🛡️ Architecture Decision Coverage Matrix

This matrix maps architectural decisions to their corresponding automated test suite and enforcement mechanism.

| Architectural Decision | ADR | Automated Test Suite | Enforcement Mechanism |
| :--- | :--- | :--- | :--- |
| **Provider Isolation** | ADR-0006, ADR-0008 | `tests/architecture/test_import_boundaries.py` | Import Linter (`.importlinter`) & Rule A001 AST Test |
| **Brain Runtime Domain DAG** | ADR-0008 | `tests/architecture/test_dependency_graph.py` | AST DAG Dependency Test |
| **Stateless Execution Pipeline** | ADR-0008 | `tests/unit/brain/test_pipeline.py` | Unit Test |
| **ExecutionContext Field Budgets** | ADR-0008, ADR-0009 | `tests/architecture/test_runtime_context.py` | AST Field Budget Test ($\le 5$ fields per sub-context) |
| **WorkingMemory Context Isolation** | ADR-0009 | `tests/architecture/test_runtime_context.py` | AST WorkingMemory Isolation Test |
| **State Ownership Single Owner** | ADR-0008, ADR-0009 | `tests/architecture/test_state_ownership.py` | AST State Ownership Test |
| **Strategy Abstraction & Protocols** | ADR-0009 | `tests/architecture/test_strategy_boundary.py` | Protocol Type Check & Builder Invariant Test |
| **Tool Port Isolation** | ADR-0009 | `tests/architecture/test_tool_boundary.py` | AST Tool Import Boundary Test |
| **State Machine Transition Matrix** | ADR-0009 | `tests/architecture/test_state_machine_matrix.py` | Transition Matrix Permutation Test |
| **Repository Layout Tooling Isolation** | AGENTS.md | `tests/architecture/test_repository_layout.py` | Import Linter (`.importlinter`) & Layout Test |
| **Distributed Cluster & Elasticity** | ADR-0014, ADR-0016 | `tests/integration/test_p5_9_multi_node_cluster.py` | Cluster Chaos & Load Test |
| **Multi-Agent Consensus & Mesh** | ADR-0017 | `tests/integration/test_p5_9_multi_node_cluster.py` | Multi-Agent Mesh Test |
| **Remote MCP SSE & Streaming** | ADR-0018 | `tests/unit/test_mcp_sse_client.py` | Unit & Mock SSE Integration Test |
| **Distributed Vector Memory** | ADR-0019 | `tests/unit/test_pgvector_store.py`, `tests/unit/test_qdrant_store.py` | Vector Compliance & Mock Adapter Suite |
| **Human Approval Webhook Gateway** | ADR-0020 | `tests/unit/infrastructure/test_webhook_approval_notifier.py` | Webhook Serialization & Resilience Suite |

---

## 📖 Guidelines for Creating New ADRs

1. File naming convention: `XXXX-short-title.md` (e.g., `0018-realtime-telemetry.md`).
2. Every ADR must contain YAML frontmatter (`status`, `audience`, `owner`, `applies_to`, `review_cycle`, `last_reviewed`).
3. Standard sections: **Context**, **Decision**, **Alternatives Considered**, **Consequences**, **Validation Criteria**, and **Review Phase**.
