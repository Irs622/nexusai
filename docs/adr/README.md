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
last_reviewed: 2026-08-07
---

# 📜 Architectural Decision Records (ADRs) Index

This directory documents key architectural decisions made during the design and development of the NexusAI AI Operating System.

---

## 📑 ADR Index

| ADR ID | Title | Status | Scope |
|---|---|---|---|
| [ADR 0001](file:///Users/mac/Downloads/jarfis%20projek/docs/adr/0001-plugin-system.md) | Plugin System Architecture & Lifecycle Hooks | Accepted | Plugins |
| [ADR 0002](file:///Users/mac/Downloads/jarfis%20projek/docs/adr/0002-memory-storage.md) | Local SQLite Vector & Key-Value Memory Storage | Accepted | Memory |
| [ADR 0003](file:///Users/mac/Downloads/jarfis%20projek/docs/adr/0003-security-evaluator.md) | Command Security Guard & Risk Classification | Accepted | Security |
| [ADR 0004](file:///Users/mac/Downloads/jarfis%20projek/docs/adr/0004-provider-interface.md) | Model-Agnostic Provider Interface | Superseded by 0006 | Models |
| [ADR 0005](file:///Users/mac/Downloads/jarfis%20projek/docs/adr/0005-reasoning-and-observation-architecture.md) | Reasoning Engine & Observation Architecture | Accepted | Brain |
| [ADR 0006](file:///Users/mac/Downloads/jarfis%20projek/docs/adr/0006-provider-sdk.md) | Vendor-Agnostic Provider SDK Foundation & Architecture | Accepted | Provider SDK |
| [ADR 0007](file:///Users/mac/Downloads/jarfis%20projek/docs/adr/0007-canonical-model-evolution.md) | Governance Principles for Canonical Model Evolution | Accepted | Provider SDK |
| [ADR 0008](file:///Users/mac/Downloads/jarfis%20projek/docs/adr/0008-brain-runtime-architecture.md) | Stateless Brain Runtime Architecture & Execution Pipeline | Accepted | Brain Runtime |
| [ADR 0009](file:///Users/mac/Downloads/jarfis%20projek/docs/adr/0009-agent-runtime-architecture.md) | Multi-Turn Agent Runtime & Decoupled Loop Architecture | Accepted | Agent Runtime |

---

## 🛡️ Architecture Decision Coverage Matrix

This matrix maps every architectural decision to its corresponding automated test suite and enforcement mechanism.

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

---

## 📖 Guidelines for Creating New ADRs

1. File naming convention: `XXXX-short-title.md` (e.g., `0010-memory-lifecycle.md`).
2. Every ADR must contain YAML frontmatter (`status`, `audience`, `owner`, `applies_to`, `review_cycle`, `last_reviewed`).
3. Standard sections: **Context**, **Decision**, **Alternatives Considered**, **Consequences**, **Validation Criteria**, and **Review Phase**.
