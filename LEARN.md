# 🎓 Learning Guide: Building & Mastering Agentic Systems with NexusAI

> **Welcome to the NexusAI Educational Guide!**  
> This document is designed for students, developers, and researchers participating in the **GitHub Community Exchange / GitHub Learning Program**. It provides a step-by-step educational breakdown of how **NexusAI** (`v0.7.0`) is engineered—from clean architecture principles to building DAG-based autonomous AI agents, multi-tier memory intelligence, and sandboxed execution policies.

---

## 📌 Table of Contents

1. [Project Overview & Learning Objectives](#-project-overview--learning-objectives)
2. [Prerequisites & Environment Setup](#-prerequisites--environment-setup)
3. [Core Architectural Concepts](#-core-architectural-concepts)
4. [Step-by-Step Practical Tutorial](#-step-by-step-practical-tutorial)
   - [Step 1: Anatomy of a NexusAI Agent](#step-1-anatomy-of-a-nexusai-agent)
   - [Step 2: Building your First Autonomous Agent](#step-2-building-your-first-autonomous-agent)
   - [Step 3: Demystifying the DAG Execution Planner](#step-3-demystifying-the-dag-execution-planner)
   - [Step 4: Pre-Execution Plan Validation & Safety](#step-4-pre-execution-plan-validation--safety)
   - [Step 5: Multi-Tier Memory Intelligence Pipeline](#step-5-multi-tier-memory-intelligence-pipeline)
   - [Step 6: Circuit Breaker Sandboxing & Reflection](#step-6-circuit-breaker-sandboxing--reflection)
5. [Hands-On Exercises for Learners](#-hands-on-exercises-for-learners)
6. [Troubleshooting & Common Pitfalls](#-troubleshooting--common-pitfalls)
7. [Further Learning & Documentation Index](#-further-learning--documentation-index)

---

## 🎯 Project Overview & Learning Objectives

### What is NexusAI?
**NexusAI** is an open-source, model-agnostic agentic AI operating system runtime designed for production deployment, distributed execution, and capability governance. Unlike simple wrappers that invoke LLMs in a single linear loop, NexusAI structures complex goals into **Directed Acyclic Graphs (DAGs)**, validates execution safety before running, manages memory through a multi-stage pipeline, and sandboxes tool interactions with state-machine circuit breakers.

```text
NexusAI Core Engine (src/nexusai/)
   └── J.A.R.V.I.S. / Jarfis (Desktop Assistant Reference Application)
```

### What You Will Learn
By working through this repository and guide, you will master:
- **Clean Architecture for AI Systems**: Enforcing strict unidirectional dependency flows in Python 3.12+.
- **DAG-Based Planning**: How goals are decomposed into executable task nodes with strict edge dependencies (`PlanGraph`).
- **Tool Interface Abstraction**: Implementing decoupled tool execution via `IToolPort`.
- **Pre-Execution Validation**: Preventing infinite execution loops (DFS cycle detection) and token budget overruns using `PlanValidator`.
- **Memory Engineering**: Understanding 5-stage memory pipelines (`Indexer` $\rightarrow$ `Retriever` $\rightarrow$ `Ranker` $\rightarrow$ `ConflictResolver` $\rightarrow$ `Compressor` $\rightarrow$ `Assembler`).
- **Resilient AI Execution**: Implementing circuit breakers (`CLOSED`, `OPEN`, `HALF_OPEN`) and dynamic plan repairs via `ReflectionEngine`.

---

## 💻 Prerequisites & Environment Setup

### System Requirements
- **Python**: Version 3.9, 3.10, 3.11, or 3.12+
- **Git**: Installed and configured
- **Virtual Environment Tool**: `venv` or `uv`

### Step-by-Step Installation

```bash
# 1. Clone the repository
git clone https://github.com/Irs622/nexusai.git
cd nexusai

# 2. Create and activate a Python virtual environment
python3 -m venv .venv
source .venv/bin/activate   # On Windows: .venv\Scripts\activate

# 3. Install dependencies in editable mode with development tools
pip install -e ".[dev]"

# 4. Set up environment variables
cp .env.example .env

# 5. Run test suite to verify setup
pytest tests/
```

---

## 🏛️ Core Architectural Concepts

NexusAI enforces a **top-down unidirectional Directed Acyclic Graph (DAG)** dependency hierarchy within package imports:

```text
nexusai.brain.domain (Core Entities & Interfaces)
        ▲
        │
nexusai.brain.runtime (Execution Context & State)
        ▲
        │
context / prompt / streaming / plugins / telemetry / persistence
        ▲
        │
nexusai.brain.pipeline (Execution Orchestration)
        ▲
        │
nexusai.brain.service (Composition Root & Public Entrypoint)
```

### Key Principles
1. **Domain Isolation**: `nexusai.brain.domain` MUST NOT import any other sub-package inside `brain`.
2. **Explicit Planning**: Plans are represented as inspectable, testable DAGs (`PlanGraph`).
3. **State Ownership**: Every state object has exactly ONE owner (e.g., `ExecutionContext` owned by Executor, `PromptBundle` immutable after render).
4. **Strong Typing**: 100% strict static type hints compliant with `mypy --strict`.

---

## 🚀 Step-by-Step Practical Tutorial

### Step 1: Anatomy of a NexusAI Agent

An agent interaction in NexusAI follows a clear life cycle:

```text
User Goal ──► PlanningContext ──► ExecutionPlanner ──► PlanGraph (DAG)
                                                            │
                                                     PlanValidator
                                                            │
User Output ◄── Tool Execution ◄── PlanGraphExecutionEngine ◄┘
```

1. **Goal Formulation**: The goal is wrapped inside an `AgentGoal` object.
2. **Context Creation**: `PlanningContext` bundles the goal, available tools, and budget constraints.
3. **DAG Generation**: `ExecutionPlanner` transforms the context into a `PlanGraph`.
4. **Validation**: `PlanValidator` checks for cycles, dead-ends, and resource limits.
5. **Dispatching**: `PlanGraphExecutionEngine` executes valid DAG nodes concurrently.

---

### Step 2: Building your First Autonomous Agent

Let's build a simple script that executes an autonomous goal using a mock tool port. 

Create a file named `my_first_agent.py` or inspect [`examples/basic_agent.py`](file:///Users/mac/Downloads/nexusai/examples/basic_agent.py):

```python
"""Building a custom autonomous agent with NexusAI."""

import asyncio
from nexusai.brain.domain.agent import AgentGoal, PlanningContext, PlanningGoal, PlanningResources
from nexusai.brain.planner.engine import PlanGraphExecutionEngine
from nexusai.brain.ports.tool_port import IToolPort, ToolExecutionRequest, ToolExecutionResult


class CustomToolPort(IToolPort):
    """Custom Tool Port implementing tool execution logic."""

    async def execute(self, request: ToolExecutionRequest) -> ToolExecutionResult:
        print(f"  [Tool execution] Tool Name: {request.tool_name}")
        print(f"  [Arguments]: {request.arguments}")

        # Simulate custom tool logic
        if request.tool_name == "summarize_file":
            result_payload = "Summary: System config is valid and healthy."
        else:
            result_payload = f"Executed {request.tool_name} successfully."

        return ToolExecutionResult(
            request_id=request.execution_id,
            tool_name=request.tool_name,
            success=True,
            result_data=result_payload,
        )


async def run_agent():
    print("=== Step 2: My First NexusAI Agent ===")

    # 1. Define the user's objective
    goal = AgentGoal(description="Locate, read, and summarize system configuration file")

    # 2. Package into PlanningContext with available tool capabilities
    context = PlanningContext(
        goal_component=PlanningGoal(goal=goal),
        resources_component=PlanningResources(available_tools=("summarize_file",)),
    )

    # 3. Instantiate execution engine and tool port
    engine = PlanGraphExecutionEngine()
    tool_port = CustomToolPort()

    # 4. Execute the plan graph asynchronously
    graph, results, trace = await engine.execute_plan(
        context, tool_port=tool_port, session_id="learning-session-01"
    )

    print(f"\nExecution Finished!")
    print(f"- Total DAG Nodes: {len(graph.nodes)}")
    print(f"- Steps Executed: {len(results)}")
    for res in results:
        print(f"  * Node Tool: [{res.tool_name}] -> Success: {res.success}")
        print(f"    Output: {res.result_data}")


if __name__ == "__main__":
    asyncio.run(run_agent())
```

---

### Step 3: Demystifying the DAG Execution Planner

NexusAI does not rely on opaque LLM text responses for multi-step reasoning. Instead, it uses a modular 5-stage planner:

1. **`GoalAnalyzer`**: Analyzes the raw goal, target artifacts, and domain requirements.
2. **`TaskDecomposer`**: Decomposes high-level objectives into granular steps.
3. **`DependencyResolver`**: Links tasks into a Directed Acyclic Graph (DAG) with explicit prerequisite dependencies.
4. **`ActionRanker`**: Ranks ready-to-execute nodes based on priority and execution constraints.
5. **`ExecutionPlanner`**: Synthesizes the finalized `PlanGraph`.

Try running the planner demo script:
```bash
python examples/planner_demo.py
```

Code excerpt from [`examples/planner_demo.py`](file:///Users/mac/Downloads/nexusai/examples/planner_demo.py):
```python
from nexusai.brain.planner.stages import ExecutionPlanner

planner = ExecutionPlanner()
plan_graph, trace = planner.plan(context, session_id="demo-planner")

# Inspect nodes and dependency edges in the generated DAG
for node_id, node in plan_graph.nodes.items():
    print(f"Node {node_id}: {node.step.title} | Dependencies: {node.dependencies}")
```

---

### Step 4: Pre-Execution Plan Validation & Safety

Before executing any plan, safety guardrails must verify that the plan will not crash or run indefinitely. `PlanValidator` runs deterministic static analysis against the `PlanGraph`:

- **Cycle Detection**: Ensures no infinite circular loops exist using Depth-First Search (DFS).
- **Dead-End Detection**: Verifies that every intermediate branch reaches a valid termination state.
- **Budget Compliance**: Checks if total estimated time and token usage exceed specified limits:
  - $\text{Time Budget} \le t_{\text{max}}$
  - $\text{Token Budget} \le N_{\text{max}}$

```python
from nexusai.brain.planner.validator import PlanValidator

validator = PlanValidator()
validation_result = validator.validate(plan_graph, constraints=context.constraints_component)

if validation_result.is_valid:
    print("✅ Plan is safe for execution.")
else:
    for issue in validation_result.issues:
        print(f"⚠️ Validation Issue [{issue.severity}]: {issue.message}")
```

---

### Step 5: Multi-Tier Memory Intelligence Pipeline

Agent memory in NexusAI is processed through a strict 5-stage pipeline to ensure relevant context retrieval without overwhelming token windows:

```text
Input Query
    │
    ▼
1. Indexer ──► Embeds and indexes incoming context events.
    │
    ▼
2. Retriever ──► Fetches candidate memories from long-term and working storage.
    │
    ▼
3. Ranker ──► Ranks retrieved items by relevance, recency, and importance.
    │
    ▼
4. ConflictResolver ──► Resolves contradictory facts or stale information.
    │
    ▼
5. Compressor & Assembler ──► Compresses memory items into optimal prompt context.
```

Explore [`examples/memory_demo.py`](file:///Users/mac/Downloads/nexusai/examples/memory_demo.py) to see how agent memory is indexed and retrieved dynamically.

---

### Step 6: Circuit Breaker Sandboxing & Reflection

When operating in production, third-party APIs or tools may fail, time out, or throw errors. NexusAI uses a finite state-machine **Circuit Breaker** to protect agent operations:

```text
      ┌────────────────────────────────────────┐
      │                                        │
      ▼                                        │
┌───────────┐     Failures > Threshold     ┌──────────┐
│  CLOSED   │ ───────────────────────────► │   OPEN   │
└───────────┘                              └──────────┘
      ▲                                         │
      │           Success Count Met             │ Timeout Expired
      └─────────────────────────────────────────┼──────────┐
                                                │          │
                                           ┌────▼──────────▼┐
                                           │   HALF_OPEN    │
                                           └────────────────┘
```

- **`CLOSED`**: Normal operation. Tool requests proceed normally.
- **`OPEN`**: Repeated failures detected. Tool execution is temporarily blocked to prevent cascading failures.
- **`HALF_OPEN`**: Trial period testing if downstream tools have recovered.

When a step fails during execution, `ReflectionEngine` diagnoses the expectation gap and triggers `PlanRepairEngine` to dynamically repair nodes in the `PlanGraph` without losing completed progress.

---

## 🧪 Hands-On Exercises for Learners

Reinforce your understanding of NexusAI by completing these exercises:

### Exercise 1: Implement a Web Search Tool Port
1. Subclass `IToolPort` in a new file `exercise_search.py`.
2. Add support for a `web_search` tool name that returns simulated search query results.
3. Pass `available_tools=("web_search", "summarize_file")` to `PlanningResources` and execute a 2-step plan.

### Exercise 2: Enforce Token Budget Constraints
1. Create a `PlanningConstraints` object with `token_budget_units=500`.
2. Run `PlanValidator` on a large plan graph.
3. Observe how `PlanValidator` flags token budget issues.

### Exercise 3: Inspect Event Bus Notifications
1. Run [`examples/event_bus_demo.py`](file:///Users/mac/Downloads/nexusai/examples/event_bus_demo.py).
2. Register a custom event handler for `AgentEventBus` to log whenever a DAG node starts and completes execution.

---

## 🛠️ Troubleshooting & Common Pitfalls

| Issue / Symptom | Potential Cause | Recommended Fix |
| :--- | :--- | :--- |
| `ImportError` or cyclic import error in `src/nexusai/brain/` | Violated unidirectional DAG import hierarchy. | Ensure `domain` does not import `runtime` or `pipeline`. Refer to [AGENTS.md](file:///Users/mac/Downloads/nexusai/AGENTS.md). |
| `PlanValidationError: Cycle detected` | PlanGraph contains a circular dependency loop. | Inspect node dependencies in `DependencyResolver` to ensure DAG condition holds. |
| Tool execution returns `ToolFailure` | Unhandled exception inside `IToolPort.execute()`. | Wrap tool calls in `try/except` inside your `IToolPort` implementation and return `ToolExecutionResult(success=False, ...)`. |
| `mypy` strict type check failures | Missing explicit type annotations on functions. | Ensure all parameters and return types are annotated (e.g., `def fn(x: str) -> bool:`). |

---

## 📚 Further Learning & Documentation Index

Expand your knowledge by diving deeper into the repository documentation:

- 📖 **[Architecture Specification (`docs/architecture.md`)](file:///Users/mac/Downloads/nexusai/docs/architecture.md)** — Comprehensive architectural breakdown and Mermaid diagrams.
- 📐 **[ADR Records (`docs/adr/`)](file:///Users/mac/Downloads/nexusai/docs/adr/)** — Architecture Decision Records detailing core design choices.
- ⚡ **[Performance Benchmarks (`docs/benchmarks.md`)](file:///Users/mac/Downloads/nexusai/docs/benchmarks.md)** — Empirical benchmark metrics and latency budgets.
- 🤝 **[Contribution Guidelines (`CONTRIBUTING.md`)](file:///Users/mac/Downloads/nexusai/CONTRIBUTING.md)** — Guidelines for contributing code and features.
- 🤖 **[AI Agent Rules (`AGENTS.md`)](file:///Users/mac/Downloads/nexusai/AGENTS.md)** — Rules and Zero-Amnesia Protocol for AI contributors.

---

*NexusAI is maintained under the [MIT License](file:///Users/mac/Downloads/nexusai/LICENSE).*
