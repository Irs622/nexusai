# 📊 NexusAI Agent Runtime — Measured Performance Benchmarks

> **Empirical Benchmark Specification & Reproducibility Guide**  

---

## 🖥️ Benchmark Environment

To ensure complete reproducibility of measured benchmark results, all benchmarks were executed under the following hardware & software environment:

- **Machine**: Apple Mac (Apple Silicon M-Series / 16 GB Unified Memory)
- **Operating System**: macOS (Darwin arm64)
- **Python Version**: Python 3.12+ (CPython)
- **Execution Command**: `python benchmarks/<script_name>.py`
- **Iterations**: 100 iterations (warm-up run executed prior to measurement)

---

## 1. Subsystem Benchmark Results

| Subsystem Component | Benchmark Script | Workload | Measured Throughput / Latency | Status |
| :--- | :--- | :--- | :--- | :--- |
| **ExecutionPlanner** | `benchmarks/planner_benchmark.py` | 100 DAG generation & validation iterations | **~0.15 ms** per plan (Throughput: **~6,500 plans/sec**) | `PASS` |
| **MemoryIndexer** | `benchmarks/memory_benchmark.py` | Indexing 1,000 episodic & semantic items | **~3.2 ms** total indexing time | `PASS` |
| **Memory Intelligence Pipeline** | `benchmarks/memory_benchmark.py` | Retrieval, ranking (recency decay), & context assembly | **~1.8 ms** per query | `PASS` |
| **Parallel ExecutionScheduler** | `benchmarks/scheduler_benchmark.py` | 200-node DAG dispatch (8 async workers) | **~12.4 ms** total duration (Throughput: **~16,000 nodes/sec**) | `PASS` |
| **Stress ExecutionScheduler** | `tests/stress/test_scheduler_1000_nodes.py` | 1,000-node DAG dispatch (16 async workers) | **~58.0 ms** total duration (Throughput: **~17,200 nodes/sec**) | `PASS` |

---

## 2. Benchmark Reproduction Commands

Execute the following commands in a clean virtual environment to reproduce these metrics:

```bash
# 1. Run Planner Pipeline Benchmark
python benchmarks/planner_benchmark.py

# 2. Run Memory Intelligence Benchmark
python benchmarks/memory_benchmark.py

# 3. Run Parallel Execution Scheduler Benchmark
python benchmarks/scheduler_benchmark.py

# 4. Run High-Concurrency Stress Suite
pytest tests/stress -m stress
```

---

## 2a. Audit Store Event-Loop Responsiveness (AUDIT-11)

**Target:** concurrent audit writes must not stall the asyncio event loop. A 1 ms sleep probe stands in for `/health/live`.
**Methodology:** `python -m benchmarks.audit_store_loop_lag --writes 400 --concurrency 50`, file-backed SQLite in a temp dir. 3 runs each, Apple Silicon macOS, Python 3.12, 2026-10-11.

| Implementation | Probe samples | p50 lateness | p95 lateness | p99 lateness | max |
|---|---|---|---|---|---|
| Before (sync `sqlite3` on loop) | 10 | 0.14–0.17 ms | 101–104 ms | 101–104 ms | 101–104 ms |
| After (`asyncio.to_thread`) | 124–126 | 0.03–0.04 ms | 0.14–0.16 ms | 1.7–2.2 ms | 6.4–7.7 ms |

Regression guard: `tests/integration/test_audit_store_event_loop.py` (p95 < 50 ms).

## 3. System Budgets & Performance Ceilings

NexusAI enforces systemic performance ceilings to prevent runtime overhead:

- **Pipeline Overhead**: $< 2.0\text{ ms}$ per turn stage.
- **DAG Generation Overhead**: $< 1.0\text{ ms}$ per 10-node plan graph.
- **Memory Retrieval Overhead**: $< 5.0\text{ ms}$ across 10,000 indexed entries.
