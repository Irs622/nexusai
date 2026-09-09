# ADR 0022: 72-Hour Sustained Soak Testing & Chaos Injection Pipeline

## Status
Accepted

## Context
As NexusAI progresses into operational production readiness (`v1.0.0`), runtime stability must be empirically proven under continuous multi-worker execution over extended operational cycles. High-concurrency agentic workflows, long-running agent reasoning loops, SQLite persistence, and tool integrations present systemic risks:
1. **Memory Drift & Accumulation**: Memory leaks from circular references, uncollected closures, cache bloat, or native C-extension buffers can cause gradual RSS growth that exhausts host memory over 24 to 72 hours of uninterrupted execution.
2. **File Descriptor Leaks**: Tools interacting with files, subprocesses, sockets, or SQLite connection pools risk leaking file descriptors if handles are not deterministically closed during task interruptions or timeouts.
3. **Async Task Abandonment**: Unhandled exceptions, deadlocks in scheduling queues, or missing cancellation handling can result in dangling asyncio tasks lingering in memory.
4. **Fault Recovery Under Multi-Worker Concurrency**: Real-world operations routinely encounter transient failures, tool timeouts, and process interruptions. The scheduler and execution state machines must gracefully isolate and recover from failures without corrupting the DAG or crashing the runtime.

## Decision
We implement a dedicated, configurable, and automated continuous soak testing and chaos injection pipeline in `tools/run_extended_soak_test.py` and automated stress verification in `tests/stress/test_extended_soak_test.py`:

1. **Configurable Continuous Execution**:
   - Accepts flexible execution durations (`--duration 30s`, `15m`, `1h`, `24h`, `72h`), target cycles (`--cycles`), and worker concurrency (`--workers 4`).
   - Executes synthetic diamond DAG workloads across `ExecutionScheduler` multi-worker pools to stress dependency resolution and concurrent branch scheduling.

2. **Multi-Mode Chaos & Fault Injection (`ChaosToolPort`)**:
   - Injects stochastic faults during tool execution based on a configurable chaos probability rate (`--chaos-rate`):
     - `TOOL_TIMEOUT`: Simulates tool latency exceeding operational thresholds (`asyncio.TimeoutError`).
     - `DAG_STEP_FAILURE`: Simulates deterministic tool logic failures (`success=False`).
     - `WORKER_EXCEPTION`: Simulates unhandled worker runtime exceptions (`RuntimeError`).
     - `CANCELLATION`: Simulates task cancellation interruptions (`asyncio.CancelledError`).
   - Tracks detailed fault recovery counters (`injected_total`, `timeouts_handled`, `step_failures_handled`, `worker_exceptions_handled`, `cancellations_handled`) to verify zero unhandled crashes.

3. **Memory Profiling & Bounded Drift Enforcement**:
   - Uses `tracemalloc` for line-by-line memory allocation tracking, taking periodic snapshots and computing differential call-site statistics (`compare_to`) against the initial baseline.
   - Measures initial and final process RSS memory via `psutil`.
   - Computes normalized 24-hour RSS drift: $\text{growth\_pct\_per\_24h} = \frac{\Delta\text{RSS}}{\text{RSS}_0} \times \frac{24}{\text{hours}}$.
   - Enforces a strict acceptance threshold: $\text{net RSS growth} < 5.0\%$ per 24 hours.
   - Provides optional integration with `memray` when installed.

4. **Resource Stability & Garbage Collection Audit**:
   - Verifies file descriptor stability by tracking open file descriptors (`psutil.Process.num_fds`), enforcing $\Delta\text{FDs} \le 2$ across thousands of cycles.
   - Performs garbage collection audits ensuring zero uncollected cyclic garbage objects (`gc.garbage == 0`).
   - Enforces task containment ensuring no dangling or leaked background asyncio tasks at run completion ($\text{lingering tasks} \le 2$).

5. **Automated Evidence Reporting**:
   - Automatically exports structured JSON telemetry (`extended_soak_report.json`) containing memory statistics, FD metrics, chaos audits, and latency percentiles (P50, P95, P99).
   - Generates formatted Markdown summaries (`extended_soak_report.md`) with tables detailing latency drift, top tracemalloc diffs, and health status verdicts.

## Alternatives Considered
- **Reusing Lightweight Burst Soak (`run_soak_test.py`)**: The existing `run_soak_test.py` was designed for short 5-second smoke runs without chaos simulation, file descriptor leak tracking, or configurable tracemalloc diff snapshots. Preserving `run_soak_test.py` for fast regression while establishing `run_extended_soak_test.py` provides a dedicated pipeline for 1h, 24h, and 72h continuous operational validation.
- **External Chaos Monkey Tooling**: Running external container chaos daemons (Chaos Mesh or Litmus). Rejected because in-process chaos injection directly tests the Python event loop, cancellation tokens, and scheduler exception isolation without requiring Kubernetes or external infrastructure dependencies.

## Consequences

### Positive
- **Empirical Operational Confidence**: Verifies that multi-worker execution remains stable, leak-free, and resilient across days of continuous load.
- **Root Cause Isolation**: Tracemalloc snapshot diffs pinpoint exact line numbers of retained memory allocations during sustained runs.
- **Proactive Leak Prevention**: Continuous monitoring of RSS, heap, file descriptors, and asyncio tasks catches memory and resource leaks before production deployment.
- **Standardized Reporting**: Automated JSON and Markdown artifacts integrate directly into CI/CD performance regression tracking.

### Negative
- **Profiling Overhead**: Running `tracemalloc` continuously with stack depth 25 adds slight CPU and memory overhead during long test runs; snapshot intervals are throttled (e.g. hourly) to minimize performance interference.

## Validation Criteria
- Execution of `tests/stress/test_extended_soak_test.py` passing 100% with:
  - Overall verdict `PASS`.
  - Normalized RSS memory growth $< 5.0\%$ per 24 hours.
  - Zero uncollected garbage objects (`gc.garbage == 0`).
  - Zero dangling asyncio tasks.
  - Zero file descriptor leaks ($\Delta\text{FDs} \le 2$).
  - Full recovery from injected chaos (timeouts, step failures, worker crashes, cancellations).
  - Valid `extended_soak_report.json` and `extended_soak_report.md` generation.
- CLI verification: `tools/run_extended_soak_test.py --duration 3s --workers 4 --chaos-rate 0.20` exiting with returncode 0.
- Architecture fitness verification passing with 100/100 score (`tools/run_architecture_tests.py`).
- Static analysis clean under `mypy --strict`, `ruff check`, and `black --check`.

## Review Phase
- **Implementation Phase**: Milestone 3+ Operational Resilience & Continuous Soak Testing.
- **Reviewers**: Architecture & Reliability Core Teams.
