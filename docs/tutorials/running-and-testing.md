---
status: stable
audience:
  - developers
  - contributors
  - devops
owner:
  - core-team
applies_to:
  - repository-wide
review_cycle: quarterly
last_reviewed: 2026-09-09
---

# 📖 Complete Guide: Running & Testing NexusAI

This guide provides end-to-end instructions for launching the NexusAI agent runtime across multiple execution modes (CLI, Web OS Dashboard, Docker, Python SDK) and executing the tiered test suite and CI quality gates.

---

## 🚀 Part 1: Running NexusAI

### 1. Environment Setup

NexusAI targets **Python 3.12+**. Follow these steps to prepare your local environment:

```bash
# 1. Clone the repository
git clone https://github.com/Irs622/nexusai.git
cd nexusai

# 2. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Upgrade build tooling and install package with development dependencies
pip install --upgrade pip setuptools wheel
pip install -e ".[dev]"

# 4. Copy the environment configuration template
cp .env.example .env
```

> **Tip**: Configure your LLM provider credentials in `.env` (such as `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, or `OPENROUTER_API_KEY`). For zero-cost local execution, NexusAI natively supports local Ollama models and offline mock execution out of the box.

---

### 2. Operational Execution Modes

#### Mode A: Interactive CLI Chat (Terminal)
Chat directly with the autonomous agent personality inside your terminal:
```bash
nexusai chat
```

Useful operational CLI commands:
- `nexusai status` — Display system health, active environment, and default model configuration.
- `nexusai cluster top` — Launch the live Terminal UI (TUI) to monitor distributed worker nodes, active leases, and task queues.
- `nexusai cluster status` — Inspect the health and heartbeat state of worker cluster nodes.
- `nexusai mcp list` — List all configured Model Context Protocol (MCP) servers and tools.
- `nexusai mcp ping filesystem` — Test connectivity to a specific MCP server.

#### Mode B: Web OS Dashboard & Real-Time SSE Stream
Run the FastAPI web backend with static asset serving and real-time Server-Sent Events (SSE) telemetry:
```bash
make web
# Or run uvicorn directly:
uvicorn nexusai.api.server:app --host 0.0.0.0 --port 8000 --reload
```
Navigate to your browser at: **`http://localhost:8000`**

#### Mode C: Containerized Deployment (Docker & Docker Compose)
Launch the isolated production runtime with persistent SQLite/WAL volume and Redis worker coordination:
```bash
# 1. Start the containerized stack
docker compose up -d

# 2. Verify health and readiness probes
curl http://localhost:8080/health/live
# Expected response: {"status":"ok"}

curl http://localhost:8080/health/ready
# Expected response: {"status":"ready"}

curl http://localhost:8080/api/status
# Expected response: JSON payload showing operational runtime state

# 3. Tear down the stack when finished
docker compose down
```

#### Mode D: Standalone Python SDK Scripts
Execute standalone workflow demonstrations:
```bash
# Run basic agent loop
python examples/basic_agent.py

# Run DAG planner and execution engine demo
python examples/planner_demo.py

# Run hybrid memory indexing and retrieval demo
python examples/memory_demo.py
```

---

## 🧪 Part 2: Testing & Quality Assurance

NexusAI enforces rigorous architectural governance (**Phase 3.2+ Architectural Governance**). Tests are organized into clean, tiered suites:

### 1. Automated Verification Gates (Recommended)

Before submitting a Pull Request (PR) or preparing a release, run both primary automated gates:

```bash
# Master Quality Gate: Linter, Formatter, Static Type Checker, 604 Unit Tests, & Benchmarks
python tools/run_quality_gate.py

# 6-Gate Release Candidate Verification Gate (Git Sanitization, Type Integrity, ADRs, Subsystems, Chaos, Wheel Build)
python tools/verify_release.py
```

---

### 2. Tiered Pytest Matrix

All test suites can be executed directly via `pytest`:

| Test Suite | Command | Description |
| :--- | :--- | :--- |
| **Integration Suite** | `pytest tests/integration -v` | **104 E2E Scenarios**: DAG topological scheduler, crash recovery resume, cryptographic audit chain tamper detection, and multi-session memory concurrency. |
| **Local Unit Suite** | `pytest (run_tests.py --mode=local)` | **604 Unit Tests**: Validates internal logic across `brain`, `runtime`, `planner`, `infrastructure`, and `tools`. |
| **Security Suite** | `pytest tests/security -v` | **67 Security Scenarios**: Filesystem sandbox escape prevention, SSRF network destination allowlists, prompt injection defense, and human-in-the-loop approval gates. |
| **Contract Suite** | `pytest tests/contracts -v` | **32 Contract Tests**: Verifies wire-format and protocol conformance across OpenAI, Gemini, Anthropic, Ollama, and OpenRouter providers. |
| **API Compatibility** | `pytest tests/api_compatibility -v` | Snapshot tests verifying backward-compatibility of public API models and schemas. |
| **Architecture Tests** | `pytest tests/architecture -v` | Verifies dependency complexity, layer boundaries, and DAG import invariants. |

---

### 3. Architecture Boundary Enforcement (Rules A001–A020)

NexusAI strictly enforces unidirectional DAG dependencies (e.g., the `providers` package MUST NOT import `runtime`):

```bash
# 1. Audit import dependencies for boundary violations
python tools/audit_dependencies.py

# 2. Run full architecture fitness test suite and compute Technical Debt Score
python tools/run_architecture_tests.py
```

---

### 4. Performance Benchmarks & Soak Testing

```bash
# Verify performance regressions (Startup Time, RSS Memory, Tool Latency) against baseline
python benchmarks/check_regressions.py

# Run continuous endurance soak test harness (100 cycles)
python tools/run_soak_test.py --cycles 100
```

---

### 5. Targeted & Granular Debugging Tips

When iterating on a specific feature or bugfix:

```bash
# Run a single test file
pytest tests/integration/test_p4_7_audit_chain.py -v

# Filter and run a specific test by name (-k)
pytest tests/integration/test_p4_7_audit_chain.py -k "test_audit_chain_tamper_detection" -v

# Stream log output in real-time (-s) and halt on first failure (-x)
pytest tests/unit/brain/test_agent_loop.py -v -s -x
```

---

### 6. Automated Code Formatting & Linting

Ensure strict code formatting and zero lint issues before committing:

```bash
# Auto-format codebase using Black and isort
python tools/run_formatter.py --fix

# Run Ruff static linter
python tools/run_linter.py

# Run MyPy strict type checker
python tools/run_typecheck.py
```
