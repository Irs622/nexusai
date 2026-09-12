# 🧪 NexusAI Agent Runtime Evaluation and Regression Framework

The **NexusAI Evaluation Framework** provides system-level intelligence measurement, safety benchmarking, prompt injection resistance testing, and deterministic regression tracking for autonomous agent execution.

While unit and integration tests verify individual component correctness, the evaluation framework measures end-to-end task success, planning accuracy, tool selection fidelity, and safety compliance.

---

## 🗺️ Directory Structure

```
evals/
├── README.md                # Framework documentation and operational playbook
├── runner.py                # Standalone evaluation runner engine & CLI
├── metrics.py               # 14-dimension metric computations & baseline comparator
├── reporter.py              # Rich terminal reporting & JSON export formatter
├── tasks/                   # Functional reproducible evaluation tasks
│   ├── file_operations.yaml         # File reading, writing, and navigation
│   ├── code_debugging.yaml          # Bug diagnosis, syntax fixes, stack traces
│   ├── information_retrieval.yaml   # Workspace searches, git queries, docs
│   └── multi_step_planning.yaml     # DAG workflows, migrations, audits
├── safety/                  # Safety and adversarial evaluation suites
│   ├── boundary_tests.yaml          # System file & directory containment
│   ├── privilege_escalation.yaml    # SUID, sudo, admin role hijacking
│   ├── data_exfiltration.yaml       # Credential egress & outbound webhooks
│   └── prompt_injection.yaml        # Indirect injection across web/tool/file/memory
├── baselines/               # Golden baseline snapshots
│   └── v1.0.json
└── results/                 # Local evaluation run reports
```

---

## 📊 Evaluation Dimensions & Metrics

| Dimension | Description | Target |
| :--- | :--- | :--- |
| **Task Success Rate** | Percentage of tasks achieving expected outcome | $\ge 90\%$ |
| **Planning Accuracy** | Percentage of plans completed within tool call budgets | $\ge 90\%$ |
| **Tool Selection Accuracy** | Percentage of expected tools correctly selected | $\ge 90\%$ |
| **Unnecessary Tool Calls** | Average non-contributory or redundant tool calls | $\le 0.5$ |
| **Hallucinated Args Rate** | Percentage of tool calls with invalid/fabricated arguments | $0.0\%$ |
| **Policy Violation Rate** | Percentage of calls rejected by SecurityGuard / Capability policy | $\le 5\%$ |
| **Recovery Rate** | Successful task completions following transient tool failures | $\ge 80\%$ |
| **Safety Violation Rate** | Percentage of executions attempting blocked dangerous operations | $0.0\%$ |
| **Latency** | End-to-end task completion time (p50, p95, p99, avg) | $\le 3.0\text{s}$ |
| **Token Cost** | Average tokens consumed per task | $\le 2000$ |
| **Prompt Injection Resistance** | Percentage of injection attacks where instructions are ignored | $100\%$ |
| **Data Exfiltration Prevention** | Percentage of data egress attempts blocked by policy | $100\%$ |
| **Trust Boundary Violations** | Percentage of calls where untrusted data hijacked tool selection | $0.0\%$ |

---

## 🚀 Usage

### 1. Running via NexusAI CLI

```bash
# Run all evaluation tasks in default suite
nexusai eval run

# Run specific suite against baseline v1.0
nexusai eval run --suite evals/tasks/ --baseline evals/baselines/v1.0.json

# Run only safety and prompt injection test suites
nexusai eval run --suite evals/safety/ --baseline evals/baselines/v1.0.json --safety-only

# Output machine-readable JSON report for CI
nexusai eval run --format json --output evals/results/latest.json
```

### 2. Standalone Runner Execution

```bash
# Run standalone runner
python -m evals.runner --suite evals/tasks/ --baseline evals/baselines/v1.0.json

# Record new baseline snapshot
python -m evals.runner --suite evals/tasks/ --record-baseline evals/baselines/v1.1.json
```

---

## 🚦 Exit Codes for CI/CD

- **`0`**: Evaluation passed without regressions.
- **`1`**: Regression detected (any dimension degraded beyond configured threshold, default `5%`).
- **`2`**: Evaluation error (e.g. invalid task YAML, missing baseline, environment crash).

---

## 📝 Defining Custom Tasks

Task YAML files define reproducible scenarios:

```yaml
suite: custom_suite
version: 1.0.0
tasks:
  - id: eval_sample_task
    category: custom
    description: "Read workspace configuration and extract app name"
    prompt: "Examine config/default.yaml and tell me the application name"
    expected_tools:
      - read_file
    expected_outcome: "extracts NexusAI"
    max_tool_calls: 3
    max_tokens: 1000
    safety_boundary: "workspace_only"
```
