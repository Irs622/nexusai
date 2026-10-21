# 🤖 NexusAI

<p align="center">
  <img src="https://github.com/user-attachments/assets/1c70af68-177f-4324-add0-dc9e09d92d94" alt="NexusAI Architecture and Dashboard" width="100%" />
</p>

<p align="center">
  <strong>Model-Agnostic Agent Runtime & Orchestration Infrastructure</strong>
</p>

<p align="center">
  An extensible Python runtime for agent planning, DAG-based execution, capability governance, and distributed AI workflows.
</p>

<p align="center">
  <a href="CHANGELOG.md"><img src="https://img.shields.io/badge/version-v1.0.0-green.svg" alt="Version 1.0.0" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="MIT License" /></a>
  <a href="pyproject.toml"><img src="https://img.shields.io/badge/python-3.12%2B-blue.svg" alt="Python 3.12+" /></a>
  <a href="docs/architecture.md"><img src="https://img.shields.io/badge/architecture-clean-purple.svg" alt="Clean Architecture" /></a>
  <a href="https://github.com/astral-sh/ruff"><img src="https://img.shields.io/badge/code%20style-Ruff-black.svg" alt="Ruff" /></a>
  <a href="https://mypy-lang.org/"><img src="https://img.shields.io/badge/type%20checking-mypy--strict-blue.svg" alt="Mypy Strict" /></a>
</p>

NexusAI is an open-source, model-agnostic agent runtime designed to coordinate AI-driven workflows through explicit planning, structured execution, and capability-based governance.

Rather than coupling agent behavior to a single model provider or application, NexusAI separates planning, execution, memory, security policies, and infrastructure behind modular interfaces.

The project targets production-oriented agent infrastructure, with ongoing validation of distributed deployments, external telemetry integrations, and multi-cloud operation.

> **Project status:** `v1.0.0 Release Candidate`. See the current testing results, release verification, and deployment documentation before using NexusAI in production environments.

---

## Table of Contents

- [Architecture Overview](#-architecture-overview)
- [Key Features](#-key-features)
- [Technology Stack](#-technology-stack)
- [Getting Started](#-getting-started)
- [Running NexusAI](#-running-nexusai)
- [Basic Usage](#-basic-usage)
- [Testing and Quality Assurance](#-testing-and-quality-assurance)
- [Deployment and Production Readiness](#-deployment-and-production-readiness)
- [Current Scope and Roadmap](#-current-scope-and-roadmap)
- [Documentation](#-documentation)
- [Contributing](#-contributing)
- [License](#-license)

---

## 🏗️ Architecture Overview

NexusAI separates the underlying agent infrastructure from the applications built on top of it.

```text
┌──────────────────────────────────────────────┐
│          Applications & Interfaces           │
│       CLI · Web Dashboard · Desktop Apps     │
├──────────────────────────────────────────────┤
│                  NexusAI                     │
│             Agent Runtime Core               │
├──────────────────────────────────────────────┤
│ Planning · Execution · Memory · Governance   │
├──────────────────────────────────────────────┤
│ Tools · Plugins · Model Providers · Storage  │
├──────────────────────────────────────────────┤
│ Infrastructure · Observability · Deployment │
└──────────────────────────────────────────────┘
```

### Runtime and Reference Application

NexusAI is the core runtime. **J.A.R.V.I.S. (Jarfis)** is the default personal desktop assistant reference application intended to run on top of this infrastructure.

- **NexusAI:** The reusable Python framework and runtime engine.
- **J.A.R.V.I.S. / Jarfis:** The assistant application and user-facing experience built using NexusAI capabilities.

This separation allows the runtime to support different interfaces and agent applications without tying its core architecture to one assistant personality.

For implementation details, see the [Architecture Specification](docs/architecture.md).

---

## ✨ Key Features

### 🧠 Intelligent Planning

- **DAG-based planning:** Represents multi-step tasks as inspectable Directed Acyclic Graphs (`PlanGraph`).
- **Multi-stage planning pipeline:** Uses goal analysis, task decomposition, dependency resolution, action ranking, and execution planning.
- **Dynamic capability discovery:** Discovers available tools and constructs capability graphs at runtime.
- **Pre-execution validation:** Checks graph cycles, dead ends, and token budget constraints before execution.
- **Reflection and plan repair:** Diagnoses expectation gaps and supports dynamic DAG node updates.

### ⚙️ Execution and Coordination

- **Asynchronous scheduling:** Executes independent DAG branches concurrently.
- **Execution state management:** Tracks workflow progress and execution outcomes.
- **Event-driven architecture:** Coordinates subsystems through asynchronous publish-subscribe domain events.
- **Resilience policies:** Uses circuit breakers with `CLOSED`, `OPEN`, and `HALF_OPEN` states.
- **Idempotency support:** Helps prevent duplicate execution when supported by the relevant execution path.

### 🗃️ Multi-Tier Memory

NexusAI organizes memory processing into a multi-stage pipeline:

`Indexer → Retriever → Ranker → Conflict Resolver → Compressor → Assembler`

This architecture separates retrieval, ranking, conflict handling, and context assembly into components that can be developed and tested independently.

### 🔐 Security and Capability Governance

- Capability-oriented tool access.
- Runtime execution policies and approval workflows.
- Role-based access control and tenant context.
- Audit event tracking and integrity verification.
- Configurable tool execution restrictions.

Security controls must be validated against the actual deployment configuration and threat model. Their presence in the architecture does not, by itself, establish security certification.

### 📡 Observability

- Execution spans and latency breakdowns.
- Runtime event streaming through Server-Sent Events (SSE).
- Structured application and audit logging.
- Integration points for OpenTelemetry-compatible tracing.

---

## 🧰 Technology Stack

| Component | Technology |
|---|---|
| Language | Python 3.12+ |
| API framework | FastAPI |
| Data validation | Pydantic |
| Asynchronous execution | Python `asyncio` |
| Coordination infrastructure | Redis |
| Execution persistence | SQLite |
| Containerization | Docker and Docker Compose |
| Orchestration | Kubernetes and Helm |
| Code quality | Ruff and Mypy |
| Testing | Pytest |
| Observability | OpenTelemetry-compatible tracing structures |

See [`pyproject.toml`](pyproject.toml) and the deployment documentation for the authoritative dependency and configuration details.

---

## 🚀 Getting Started

### Prerequisites

- Python 3.12 or newer.
- Git.
- `pip` and Python virtual environment support.
- Docker and Docker Compose for containerized deployment.

### 1. Clone the Repository

```bash
git clone https://github.com/Irs622/nexusai.git
cd nexusai
```

### 2. Create a Virtual Environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

On Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

### 3. Install NexusAI

```bash
python -m pip install --upgrade pip setuptools wheel
pip install -e ".[dev]"
```

### 4. Configure the Environment

```bash
cp .env.example .env
```

Review `.env` and the configuration files before running the application. Add provider credentials only when required by the selected model integration.

Do not commit `.env` or real API keys to version control.

### 5. Run the Offline Example

```bash
python examples/basic_agent.py
```

The basic example uses a mock tool implementation and demonstrates the planning and execution flow without requiring a live external tool.

---

## 🖥️ Running NexusAI

NexusAI provides several execution and interaction modes.

| Mode | Command | Purpose |
|---|---|---|
| Interactive CLI | `nexusai chat` | Interact with the agent through a terminal |
| Web dashboard | `make web` | Start the web interface |
| Development API | `uvicorn nexusai.api.server:app --port 8000 --reload` | Run the API locally |
| Docker Compose | `docker compose up -d` | Start the containerized runtime and coordination services |
| Cluster monitor | `nexusai cluster top` | Inspect worker and lease information |

For local development, open `http://localhost:8000` after starting the web application.

**Deployment note:** The Docker Compose command should not be treated as production-ready merely because it starts successfully. Review environment settings, secrets, network exposure, persistence, and health checks before exposing services to a public network.

---

## 💻 Basic Usage

The following example demonstrates how to construct a planning context and execute a plan through a mock tool port.

```python
import asyncio

from nexusai.brain.domain.agent import (
    AgentGoal,
    PlanningContext,
    PlanningGoal,
    PlanningResources,
)
from nexusai.brain.planner.engine import PlanGraphExecutionEngine
from nexusai.brain.ports.tool_port import (
    IToolPort,
    ToolExecutionRequest,
    ToolExecutionResult,
)


class MockToolPort(IToolPort):
    async def execute(
        self,
        request: ToolExecutionRequest,
    ) -> ToolExecutionResult:
        return ToolExecutionResult(
            request_id=request.execution_id,
            tool_name=request.tool_name,
            success=True,
            result_data="Output OK",
        )


async def main() -> None:
    goal = AgentGoal(
        description="Locate, read, and summarize a config file"
    )

    context = PlanningContext(
        goal_component=PlanningGoal(goal=goal),
        resources_component=PlanningResources(
            available_tools=("summarize_file",),
        ),
    )

    engine = PlanGraphExecutionEngine()

    graph, results, trace = await engine.execute_plan(
        context,
        tool_port=MockToolPort(),
    )

    print(f"Plan executed with {len(results)} steps.")


if __name__ == "__main__":
    asyncio.run(main())
```

This example uses a mock implementation. It demonstrates the planning and tool-port interface, not actual file access or a live model-provider integration.

For additional examples, explore [`examples/`](examples/).

---

## 🧪 Testing and Quality Assurance

NexusAI includes tooling for automated testing, code quality checks, release verification, and architectural boundary validation.

Run the checks locally before submitting changes.

### 1. Master Quality Gate

```bash
python tools/run_quality_gate.py
```

The documented quality gate covers linting, formatting, static type checking, unit tests, and benchmarks.

### 2. Release Candidate Verification

```bash
python tools/verify_release.py
```

### 3. Integration Tests

```bash
pytest tests/integration -v
```

### 4. Architecture Boundary Checks

```bash
python tools/audit_dependencies.py
python tools/run_architecture_tests.py
```

The repository documentation describes a suite of 604 unit tests and 104 integration, end-to-end, and chaos tests. Treat these as documented suite sizes, not proof that the current commit passes.

Use actual command output and CI results to confirm the current test status.

For more information, see the [Running & Testing Guide](docs/tutorials/running-and-testing.md).

---

## ☸️ Deployment and Production Readiness

NexusAI includes infrastructure intended to support containerized and orchestrated deployments.

- **Docker Compose:** Local multi-service deployment.
- **Kubernetes and Helm:** Deployment configuration for cluster environments.
- **Persistent execution state:** Storage components for execution records and coordination.
- **Runtime governance:** Policies and approval workflows for controlled execution.

Before a production deployment, validate at least the following:

- Authentication and authorization for every sensitive endpoint.
- Tenant isolation across execution, memory, and audit operations.
- Tool execution boundaries and approval token lifecycle.
- Persistent storage, backup, and recovery behavior.
- Redis network exposure and access controls.
- Production configuration and secret management.
- Resource limits, concurrency, timeouts, and failure recovery.
- Monitoring, tracing exports, and operational alerts.

See [`deploy/helm/nexusai/`](deploy/helm/nexusai/) and [`docker-compose.yml`](docker-compose.yml) for the current deployment configuration.

---

## 🛣️ Current Scope and Roadmap

NexusAI is under active development. The following limitations and milestones are documented in the project.

| Area | Current scope |
|---|---|
| Distributed execution | Docker and Kubernetes deployment support; live multi-cloud validation remains ongoing |
| External telemetry | Native Jaeger/Zipkin exporter integrations are in development |
| Policy optimization | Dataset win-rate heuristics are used rather than full deep reinforcement learning |
| Performance evaluation | Benchmarks currently focus on single-machine test environments |

These distinctions are important when evaluating the framework for production use. Deployment manifests, simulation modes, and architectural interfaces do not automatically establish validated distributed operation.

See the [Product Roadmap](ROADMAP.md) and [Performance Benchmarks](docs/benchmarks.md) for additional details.

---

## 📚 Documentation

| Resource | Description |
|---|---|
| [Architecture Specification](docs/architecture.md) | Architecture layers, boundaries, and execution pipeline |
| [Running & Testing Guide](docs/tutorials/running-and-testing.md) | Setup, execution modes, tests, and debugging |
| [Framework Comparison](docs/why-nexusai.md) | Comparison with LangGraph, AutoGen, CrewAI, and Haystack |
| [Performance Benchmarks](docs/benchmarks.md) | Benchmark methodology, metrics, and reproducibility |
| [Examples](examples/) | Standalone examples for planning, memory, and runtime behavior |
| [Product Roadmap](ROADMAP.md) | Milestones and planned improvements |
| [Changelog](CHANGELOG.md) | Release history |
| [Contributing Guide](CONTRIBUTING.md) | Development setup and contribution workflow |
| [Agent Contribution Guide](AGENTS.md) | Instructions for AI-assisted contributions |
| [Support](SUPPORT.md) | Support channels and project questions |
| [Code of Conduct](CODE_OF_CONDUCT.md) | Community participation guidelines |

---

## 🤝 Contributing

Contributions, bug reports, and architectural discussions are welcome.

Before opening a pull request:

1. Read [`CONTRIBUTING.md`](CONTRIBUTING.md).
2. Follow the project conventions described in [`AGENTS.md`](AGENTS.md) when using AI coding agents.
3. Add or update tests for behavioral changes.
4. Run the relevant quality and architecture checks.
5. Document security-sensitive changes and their assumptions.

Please report security vulnerabilities through the project's designated security reporting process rather than publishing exploitable details in a public issue.

---

## 📜 License

NexusAI is distributed under the [MIT License](LICENSE).

---

<p align="center">
  <strong>NexusAI</strong>
  <br />
  Model-agnostic agent infrastructure, built around explicit planning, controlled execution, and testable architecture.
</p>
