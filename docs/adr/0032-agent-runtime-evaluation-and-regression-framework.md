---
status: accepted
date: 2026-09-12
decision-makers:
  - evaluation-lead
  - security-architect
  - core-team
consulted:
  - runtime-team
  - qa-team
informed:
  - contributors
---

# ADR 0032: Agent Runtime Evaluation and Regression Framework

## Status
Accepted

## Context
NexusAI maintains extensive automated testing suites—unit, integration, stress, security, snapshot, and architecture DAG tests. However, prior to this decision, none of these tests measured whether the agent runtime actually performs well as an intelligent autonomous system.
- Unit tests verify component correctness in isolation.
- Contract tests verify schema adherence.
- Security tests verify exploit blocking.

Without an evaluation framework, changes to the planner, runtime, memory, prompt builders, or tool selection could silently degrade agent reasoning quality, tool accuracy, or safety resilience with zero signal in CI/CD pipelines.

To establish system-level intelligence tracking, Issue #35 mandates an **Agent Runtime Evaluation and Regression Framework** providing quantitative measurements across task completion, planning accuracy, tool selection, safety boundaries, and prompt-injection resistance.

## Decision
We establish a dedicated, repository-isolated evaluation framework under `evals/` accompanied by a unified CLI subcommand `nexusai eval run`.

### 1. Repository Layout and Package Isolation (Rule 8 Compliance)
In strict compliance with **AGENTS.md Rule 8 (Tooling Package Isolation)**:
- The `evals/` package is located at the repository root outside `src/` to prevent evaluation harnesses, task YAMLs, and benchmark scripts from becoming production runtime dependencies.
- Production application code under `src/nexusai` does not import `evals/`.
- The CLI subcommand (`nexusai.cli.eval_cmd`) lazily imports the evaluation runner at invocation time.

### 2. Evaluation Dimensions
The framework tracks 14 distinct quantitative dimensions across every run:
1. **Task Success Rate (%)**: Percentage of evaluation tasks completed according to specified success criteria.
2. **Planning Accuracy (%)**: Degree to which resolved DAG execution plans adhered to step constraints.
3. **Tool Selection Accuracy (%)**: Precision of invoked tools against expected tool suites.
4. **Unnecessary Tool Calls (avg)**: Average count of redundant or irrelevant tool invocations per task.
5. **Hallucinated Arguments Rate (%)**: Percentage of tool calls providing parameters not present in the tool's JSON schema.
6. **Policy Violation Rate (%)**: Percentage of actions violating defensive execution policies.
7. **Recovery Rate (%)**: Success rate of self-healing or replanning when encountering initial step failures.
8. **Safety Violation Rate (%)**: Frequency of execution attempting restricted filesystem paths or unsafe commands.
9. **Execution Latency (p50, p95, p99, avg)**: Wall-clock latency distribution across evaluated tasks.
10. **Token Cost (avg)**: Average prompt and generation token consumption per task.
11. **Total Cost (USD)**: Estimated cumulative inference cost of the evaluation suite.
12. **Prompt Injection Resistance Rate (%)**: Percentage of adversarial injections ignored or safely refused.
13. **Data Exfiltration Prevention Rate (%)**: Percentage of simulated credential/token egress attempts blocked.
14. **Trust Boundary Violation Rate (%)**: Percentage of untrusted inputs causing unauthorized state transitions.

### 3. Task Suite Structure
Evaluation scenarios are declaratively specified in YAML files under `evals/`:
- **Functional Suites (`evals/tasks/`)**:
  - `file_operations.yaml`: 5 tasks (file reading, writing, directory listing, configuration parsing, log grep).
  - `code_debugging.yaml`: 5 tasks (syntax error resolution, failing test diagnosis, null check, stack trace trace, refactor).
  - `information_retrieval.yaml`: 5 tasks (symbol lookup, architectural query, git history query, dependency check, route lookup).
  - `multi_step_planning.yaml`: 5 tasks (tool scaffolding, schema migration, security audit, backup/restore, batch validation).
- **Safety Suites (`evals/safety/`)**:
  - `boundary_tests.yaml`: 4 tasks (SSH keys, root deletion, sudoers mutation, Docker socket breakout).
  - `privilege_escalation.yaml`: 3 tasks (`sudo su`, SUID permission escalation, administrative role injection).
  - `data_exfiltration.yaml`: 3 tasks (webhook `.env` egress, database dump exfiltration, AWS key pastebin egress).
  - `prompt_injection.yaml`: 6 tasks across web content, tool output, memory recall, workspace file, MCP server, and multi-hop vectors.

### 4. Baseline Comparison & CI Integration
- Evaluation runs compare current metrics against a frozen golden baseline snapshot (`evals/baselines/v1.0.json`).
- Each dimension is evaluated against a configurable regression tolerance threshold (default: 5% / 0.05).
- A dimension drops into `REGRESSION` status if its value degrades beyond the threshold.
- Deterministic exit codes govern CI pipeline gates:
  - `0`: All dimensions met or exceeded baseline targets (clean / stable / improved).
  - `1`: Performance or safety regression detected on one or more dimensions.
  - `2`: Evaluation execution error (e.g., missing baseline, invalid YAML specification).

### 5. Unified CLI Interface
The framework exposes Typer commands under `nexusai eval`:
- `nexusai eval run`: Runs evaluation suite against baseline.
- Flags:
  - `--suite, -s`: Specify target suite directory or YAML name.
  - `--baseline, -b`: Path to baseline snapshot JSON.
  - `--record-baseline`: Save current metrics as a new baseline snapshot.
  - `--safety-only`: Filter to safety and prompt injection suites only.
  - `--format, -f`: Select terminal table (`table`) or structured JSON (`json`).
  - `--output, -o`: Save results report to disk.
  - `--threshold, -t`: Configure regression tolerance threshold.

## Alternatives Considered
- **Embedding Evaluation as Pytest Suites**: *Rejected*. Pytest suites run concurrently and focus on functional assertions rather than multidimensional distribution metrics, baseline percentile comparisons, and regression drift tracking.
- **External Evaluation SaaS / Platforms**: *Rejected*. External platforms introduce third-party network dependencies, licensing overhead, and prevent offline development and air-gapped CI test runs.
- **Single Aggregate Score**: *Rejected*. A single score hides critical trade-offs (e.g. higher task success at the expense of an unacceptable safety violation rate or 300% latency regression).

## Consequences
### Positive
- Continuous quantitative signal on model and planner quality before merging PRs.
- Automatic detection of prompt injection or exfiltration regressions.
- Complete isolation from core runtime packages (`src/nexusai`).
- Flexible CLI enabling local engineer benchmarks and CI automated gating.

### Negative
- Task YAML suites and baseline snapshots must be maintained as system capabilities expand.
- Baseline snapshots require re-calibration when intentional major architecture upgrades alter token or latency distributions.

## Validation Criteria
- [x] Full test suite of 36 evaluation tasks across functional and safety categories.
- [x] Automated metric calculation across all 14 specified evaluation dimensions.
- [x] Deterministic comparison against `evals/baselines/v1.0.json` with diff reporting.
- [x] CLI command `nexusai eval run` with Rich terminal formatting and JSON output support.
- [x] Unit test coverage of runner, metric math, baseline comparison, and CLI entrypoint.

## Review Phase
Phase 3.2+ Operational Hardening.
