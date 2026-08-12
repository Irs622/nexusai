# 🤖 NexusAI

> **Model-Agnostic Agent Runtime & Orchestration Infrastructure**

[![Version](https://img.shields.io/badge/version-v0.7.0-green.svg)](CHANGELOG.md)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python Version](https://img.shields.io/badge/python-3.9%20%7C%203.10%20%7C%203.11%20%7C%203.12-blue.svg)](pyproject.toml)
[![Architecture](https://img.shields.io/badge/architecture-P5%20Production%20Deployment-purple.svg)](docs/specs/core/architecture.md)
[![Code Style: Ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)
[![Type Checked: Mypy](https://img.shields.io/badge/type--checked-mypy--strict-blue.svg)](https://mypy-lang.org/)
[![Code of Conduct](https://img.shields.io/badge/Code%20of%20Conduct-v2.1-purple.svg)](CODE_OF_CONDUCT.md)

**NexusAI** is a multi-tenant, agentic AI operating system runtime designed for production deployment, distributed execution, and capability governance.

It provides explicit DAG-based planning, execution scheduling, memory management, runtime policies, event-driven coordination, plugin capabilities, observability, and multi-provider model integration.

NexusAI is currently a production-oriented runtime architecture (`v0.6.0`). Operational validation under real-world workloads is ongoing.

Long-term, NexusAI aims to evolve from an agent runtime into a general-purpose AI Operating System.

---

### 🧩 Architecture Hierarchy & Reference Application

```text
NexusAI
    ↓ (Core Infrastructure / Agent Runtime)
J.A.R.V.I.S. / Jarfis
    ↓ (Default Desktop Assistant Personality / Reference Application)
```

- **NexusAI**: The core open-source Python framework and runtime engine.
- **J.A.R.V.I.S. (Jarfis)**: The default personal desktop assistant reference application built on top of the NexusAI engine.

---

## ⚡ Quickstart

```bash
# 1. Clone repository
git clone https://github.com/Irs622/nexusai.git
cd nexusai

# 2. Set up environment & install package
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# 3. Copy default configuration
cp .env.example .env

# 4. Run basic agent example (Offline mock execution)
python examples/basic_agent.py
```

---

## 💡 Basic Usage Example

```python
import asyncio
from nexusai.brain.domain.agent import AgentGoal, PlanningContext, PlanningGoal, PlanningResources
from nexusai.brain.planner.engine import PlanGraphExecutionEngine
from nexusai.brain.ports.tool_port import IToolPort, ToolExecutionRequest, ToolExecutionResult

class MockToolPort(IToolPort):
    async def execute(self, request: ToolExecutionRequest) -> ToolExecutionResult:
        return ToolExecutionResult(request_id=request.execution_id, tool_name=request.tool_name, success=True, result_data="Output OK")

async def main():
    goal = AgentGoal(description="Locate, read, and summarize config file")
    ctx = PlanningContext(
        goal_component=PlanningGoal(goal=goal),
        resources_component=PlanningResources(available_tools=("summarize_file",)),
    )
    engine = PlanGraphExecutionEngine()
    graph, results, trace = await engine.execute_plan(ctx, tool_port=MockToolPort())
    print(f"Plan executed successfully with {len(results)} steps!")

if __name__ == "__main__":
    asyncio.run(main())
```

---

## ✨ Key Features

- **DAG-Based Execution Planner (`PlanGraph`)**: Multi-stage planner (`GoalAnalyzer` $\rightarrow$ `TaskDecomposer` $\rightarrow$ `DependencyResolver` $\rightarrow$ `ActionRanker` $\rightarrow$ `ExecutionPlanner`) with inspectable DAG graphs.
- **Dynamic Capability Discovery**: Decouples tool execution from hardcoded names via `RuntimeCapabilityDiscovery` and ephemeral `DynamicCapabilityGraphBuilder`.
- **Parallel Async Scheduler**: Concurrently dispatches independent DAG branches using async worker pools.
- **Pre-Execution `PlanValidator`**: Enforces DFS graph cycle detection, dead-end validation, and token budget limits.
- **Runtime Policy Sandboxing**: Prevents cascading failures with state-machine circuit breakers (`CLOSED`, `OPEN`, `HALF_OPEN`).
- **Multi-Tier Memory Intelligence**: 5-stage pipeline (`Indexer` $\rightarrow$ `Retriever` $\rightarrow$ `Ranker` $\rightarrow$ `ConflictResolver` $\rightarrow$ `Compressor` $\rightarrow$ `Assembler`).
- **Expectation Reflection & Plan Repair**: `ReflectionEngine` expectation-gap diagnostics and `PlanRepairEngine` dynamic DAG node re-patching.
- **OpenTelemetry Observability**: Hierarchical `ExecutionSpan` tracking and `TraceCollector` latency breakdown markers.

---

## ⚠️ Current Limitations

- **Single-Node Execution**: Distributed worker execution across remote SSH/Docker nodes is planned for future milestones.
- **Production Telemetry Backends**: Tracing spans currently output to OpenTelemetry-compatible memory structures and logs; external Jaeger/Zipkin exporters are in active development.
- **Heuristic Strategy Tuning**: Closed-loop policy tuning currently uses dataset win-rate heuristics rather than full deep reinforcement learning.
- **Single-Machine Benchmarks**: Performance metrics are currently measured in single-machine local environments (`docs/benchmarks.md`).

---

## 💡 Philosophy & Core Principles

- **Explicit Planning**: Plans are represented as inspectable, testable Directed Acyclic Graphs (`PlanGraph`).
- **Strong Typing**: All domain interfaces enforce strict static type annotations (`mypy --strict`).
- **Event-Driven Architecture**: Subsystems communicate asynchronously via publish-subscribe domain events (`AgentEventBus`).
- **Testability Over Magic**: Deterministic replay, pre-execution validation, and static architecture complexity assertions.

---

## 📚 Documentation Index

- **[Architecture Specification (docs/architecture.md)](docs/architecture.md)** — Clean Architecture layers & Mermaid pipeline diagrams.
- **[Framework Comparison (docs/why-nexusai.md)](docs/why-nexusai.md)** — NexusAI vs. LangGraph, AutoGen, CrewAI, & Haystack.
- **[Performance Benchmarks (docs/benchmarks.md)](docs/benchmarks.md)** — Sub-millisecond empirical benchmark metrics & reproducibility instructions.
- **[Examples Directory (examples/)](examples/)** — Standalone executable demo scripts (`planner_demo.py`, `memory_demo.py`, `runtime_demo.py`).
- **[Product Roadmap (ROADMAP.md)](ROADMAP.md)** — Milestone history & `v0.6.0` $\rightarrow$ `v1.0.0` roadmap.

---

## 🤝 Contributing & Community

We welcome community contributions!
- Please read **[CONTRIBUTING.md](CONTRIBUTING.md)** for developer setup and PR workflows.
- For AI agent contributions, refer to **[AGENTS.md](AGENTS.md)**.
- For support channels and questions, see **[SUPPORT.md](SUPPORT.md)**.

---

## 📜 License

Distributed under the official **[MIT License](LICENSE)**. See `LICENSE` for details.
