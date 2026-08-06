# Engineering Quality Gate

This document is the authoritative guide for NexusAI's engineering quality standards, verification pipeline, benchmark regression system, stress testing, and repository health practices.

---

## Overview

Phase 2.6 established a comprehensive Engineering Quality Gate that every contribution must pass before merging. The quality system is composed of five independent, modular layers:

| Layer | Tool(s) | Target |
|---|---|---|
| Static Analysis | Ruff, Black, isort, MyPy | `src/`, `tests/`, `tools/`, `benchmarks/` |
| Test Coverage | pytest-cov (branch) | Overall ≥ 90%, Kernel/Memory/Core ≥ 95% |
| Mutation Testing | mutmut | `core/`, `kernel/`, `memory/domain/` only |
| Benchmark Regression | Custom Framework | Startup, RSS, Tool Latency SLAs |
| Repository Health | pip-audit, pip-licenses | CVE-free, No GPL violations |

---

## Running the Quality Gate

### Local Developer (All Stages)

```bash
python tools/run_quality_gate.py
```

This executes:
- **Stage 1 (Parallel)**: Formatter + Linter + Type Checker
- **Stage 2 (Sequential)**: Architecture → Tests & Coverage → Benchmarks

### Individual Modular Runners

```bash
# Stage 1 — Static Analysis (can run independently)
python tools/run_formatter.py          # Black & isort check
python tools/run_formatter.py --fix   # Auto-fix formatting
python tools/run_linter.py            # Ruff check
python tools/run_linter.py --fix      # Ruff auto-fix
python tools/run_typecheck.py         # MyPy strict check

# Stage 2 — Verification
python tools/run_architecture_tests.py  # Architecture boundary enforcement
python tools/run_tests.py               # Full test suite with coverage
python tools/run_tests.py --no-cov      # Fast tests without coverage
python tools/run_benchmarks.py          # Benchmark pipeline + trend report
python tools/run_benchmarks.py --quick  # Fast CI mode (fewer iterations)

# Supplemental Runners
python tools/run_mutation_tests.py      # Scoped mutation testing
python tools/run_security_audit.py     # pip-audit CVE scan
python tools/run_license_check.py      # Dependency license compliance
```

---

## Code Coverage Standards

Coverage is enforced with branch coverage enabled (`--cov-branch`).

| Package | Minimum Coverage |
|---|---|
| Overall (`src/nexusai`) | ≥ 90% |
| `src/nexusai/kernel/` | ≥ 95% |
| `src/nexusai/memory/` | ≥ 95% |
| `src/nexusai/core/` | ≥ 95% |
| `tests/acceptance/` | Excluded from coverage |

Coverage configuration is in `pyproject.toml` under `[tool.coverage.run]` and `[tool.coverage.report]`.

---

## Static Analysis Rules

### Ruff
Enforced rule groups: `E` (style), `F` (pyflakes), `W` (warnings), `I` (isort).

Configuration in `pyproject.toml`:
```toml
[tool.ruff.lint]
select = ["E", "F", "W", "I"]
```

### MyPy
All code must be `mypy --strict` compliant. No `Any` escaping without explicit justification.

```toml
[tool.mypy]
python_version = "3.12"
strict = true
warn_return_any = true
```

### Black & isort
Line length: `100`. Target version: `py312`. isort profile: `black`.

---

## Benchmark Regression System

The benchmark framework uses a pluggable pipeline:

```
BenchmarkRunner
  └── collectors/metrics.py    → collect live metrics
  └── comparators/baseline.py  → compare vs. baseline
  └── reporters/terminal.py    → render trend report + save run snapshot
```

### Baseline Files
| Location | Purpose |
|---|---|
| `benchmarks/history/baseline/` | Release baseline snapshots (committed to git) |
| `benchmarks/history/runs/` | Per-run dated snapshots (local, gitignored) |

### Performance SLA Thresholds

| Metric | Baseline Median | Max Threshold |
|---|---|---|
| CLI Startup Time | 1.21s | ≤ 1.80s |
| Memory RSS Footprint | 145.2 MB | ≤ 200 MB |
| Tool Execution Latency | 12.4ms | ≤ 50ms |

### Example Trend Report Output

```
═══════════════════════════════════════════════════════════════════
  NexusAI Benchmark Quality Gate — Trend Report
═══════════════════════════════════════════════════════════════════
  Metric                 Current     Previous    Delta      Threshold       Status
  ─────────────────────────────────────────────────────────────────
  startup_time_seconds   1.480s      1.210s      +22.31%    <= 1.8s        ✅ PASS
  memory_rss_mb          148.200MB   145.200MB   +2.07%     <= 200.0MB     ✅ PASS
  tool_latency_ms        13.200ms    12.400ms    +6.45%     <= 50.0ms      ✅ PASS
  ─────────────────────────────────────────────────────────────────

  ✅ ALL BENCHMARKS PASSED
═══════════════════════════════════════════════════════════════════
```

---

## Stress Testing

Extreme stress tests are located in [`tests/kernel/test_kernel_extreme_stress.py`](../../tests/kernel/test_kernel_extreme_stress.py).

| Test Scenario | Load |
|---|---|
| Concurrent async task submission | 10,000 tasks |
| Rapid service registration & startup | 100 services |
| Rapid shutdown under active worker load | 500 in-flight jobs |
| Queue flooding burst resilience | 5 × 1,000 burst enqueue |
| Dependency graph concurrent resolution | 100 concurrent queries |
| Registry concurrent read/write contention | 200 concurrent services |

Run stress tests:
```bash
pytest tests/kernel/test_kernel_extreme_stress.py -v
```

---

## Mutation Testing

Mutation testing is scoped **only** to core domain logic to prevent false positives:

| Included | Excluded |
|---|---|
| `src/nexusai/core/` | `src/nexusai/providers/` |
| `src/nexusai/kernel/` | `src/nexusai/cli/` |
| `src/nexusai/memory/domain/` | `src/nexusai/tools/` |
| | `benchmarks/` |

Run mutation tests:
```bash
python tools/run_mutation_tests.py
```

> [!NOTE]
> Mutation testing is compute-intensive and is **not** run on every CI push. It is scheduled weekly or manually triggered for major releases.

---

## Security & License Audits

### CVE Vulnerability Scan

```bash
python tools/run_security_audit.py
```

Powered by `pip-audit`. CI blocks merge if HIGH or CRITICAL CVEs are detected.

### License Compliance

```bash
python tools/run_license_check.py
```

| Status | License Examples |
|---|---|
| ✅ Allowed | MIT, Apache-2.0, BSD, PSF, ISC, MPL-2.0, LGPL |
| ❌ Blocked | GPL-2.0, GPL-3.0, AGPL-3.0 |

---

## Pre-Commit Hooks

Install once after cloning:

```bash
pip install pre-commit
pre-commit install
```

Pre-commit runs Ruff, Black, isort, MyPy, and file hygiene checks before every `git commit`. Configuration in [`.pre-commit-config.yaml`](../../.pre-commit-config.yaml).

---

## GitHub Actions CI Structure

| Workflow | Jobs | Trigger |
|---|---|---|
| `lint.yml` | formatter, linter, typecheck | Push + PR |
| `tests.yml` | pytest matrix (3.10, 3.11, 3.12) | Push + PR |
| `ci.yml` | Full quality gate | Push + PR (main, develop) |
| `architecture-enforcement.yml` | Architecture boundary check | Push + PR |

Each workflow calls the corresponding modular runner script to maintain single-responsibility and allow independent debugging.

---

## Updating Baselines

When a new performance improvement is validated:

```bash
# 1. Run benchmarks to get current values
python tools/run_benchmarks.py

# 2. Manually update benchmarks/history/baseline/<new-version>.json
# with the new median, p95, and max_threshold values

# 3. Commit the updated baseline
git add benchmarks/history/baseline/
git commit -m "chore: update benchmark baseline to <version>"
```

---

## Definition of Done (DoD) for Phase 2.6

- ✅ All modular runners execute without error.
- ✅ GitHub Actions CI workflows pass on all Python versions (3.10, 3.11, 3.12).
- ✅ Test coverage ≥ 90% overall.
- ✅ Stress tests complete under defined time bounds.
- ✅ Benchmark regression check passes against baseline.
- ✅ No CVE violations or license conflicts detected.
- ✅ Pre-commit hooks installed and functional.
- ✅ This document is up to date.
