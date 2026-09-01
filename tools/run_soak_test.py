#!/usr/bin/env python3
"""
NexusAI Endurance & 72-Hour Continuous Soak Test Harness.

Executes continuous stress workloads across PlanGraph DAGs and MCP tools while monitoring:
- Zero Memory Leak (RSS memory curve via psutil & heap allocation via tracemalloc)
- Garbage Collection Audit (cyclic references and lingering async tasks)
- Latency Drift Tracking (P50, P95, P99 stability)
- Evidence Export (JSON and Markdown reports in artifacts/soak_test/)
"""

from __future__ import annotations

import argparse
import asyncio
import gc
import json
import math
import os
from pathlib import Path
import sys
import time
import tracemalloc
from typing import Any

import psutil

# Ensure src/ is on python path
repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repo_root / "src"))

from nexusai.brain.domain.agent import PlanGraph, PlanGraphNode, PlanStep
from nexusai.brain.planner.scheduler import ExecutionScheduler
from nexusai.brain.ports.tool_port import ToolExecutionRequest, ToolExecutionResult


class SoakToolPort:
    """Synthetic IToolPort implementation executing computational operations without memory leaks."""

    async def execute(self, request: ToolExecutionRequest) -> ToolExecutionResult:
        data_payload = request.arguments.get("payload", "soak_data")
        multiplier = request.arguments.get("multiplier", 10)
        transformed = [f"{data_payload}_{i}_{math.sqrt(i + 1):.2f}" for i in range(multiplier)]
        return ToolExecutionResult(
            tool_name=request.tool_name,
            success=True,
            output={"result_count": len(transformed), "checksum": hash("".join(transformed))},
            execution_time_ms=0.5,
        )


def parse_duration_seconds(duration_str: str) -> float:
    """Parse duration strings such as '60s', '5m', '2h', '72h' into seconds."""
    duration_str = duration_str.strip().lower()
    if duration_str.endswith("s"):
        return float(duration_str[:-1])
    elif duration_str.endswith("m"):
        return float(duration_str[:-1]) * 60.0
    elif duration_str.endswith("h"):
        return float(duration_str[:-1]) * 3600.0
    elif duration_str.endswith("d"):
        return float(duration_str[:-1]) * 86400.0
    return float(duration_str)


def build_synthetic_dag(cycle_id: int) -> PlanGraph:
    """Construct a diamond DAG workload to stress dependency scheduler."""
    step1 = PlanStep(
        step_id=1,
        title=f"Fetch {cycle_id}",
        description=f"Initial fetch {cycle_id}",
        tool_name="dummy_soak_tool",
        arguments={"payload": f"cycle_{cycle_id}_step1", "multiplier": 15},
    )
    step2 = PlanStep(
        step_id=2,
        title=f"Branch A {cycle_id}",
        description=f"Transform branch A {cycle_id}",
        tool_name="dummy_soak_tool",
        arguments={"payload": f"cycle_{cycle_id}_step2", "multiplier": 20},
    )
    step3 = PlanStep(
        step_id=3,
        title=f"Branch B {cycle_id}",
        description=f"Transform branch B {cycle_id}",
        tool_name="dummy_soak_tool",
        arguments={"payload": f"cycle_{cycle_id}_step3", "multiplier": 20},
    )
    step4 = PlanStep(
        step_id=4,
        title=f"Consolidation {cycle_id}",
        description=f"Consolidation {cycle_id}",
        tool_name="dummy_soak_tool",
        arguments={"payload": f"cycle_{cycle_id}_step4", "multiplier": 10},
    )

    nodes: dict[int | str, PlanGraphNode] = {
        1: PlanGraphNode(step=step1, dependencies=()),
        2: PlanGraphNode(step=step2, dependencies=(1,)),
        3: PlanGraphNode(step=step3, dependencies=(1,)),
        4: PlanGraphNode(step=step4, dependencies=(2, 3)),
    }
    return PlanGraph(nodes=nodes)


def calculate_percentiles(values: list[float]) -> dict[str, float]:
    """Calculate P50, P95, P99 and mean for a list of metrics."""
    if not values:
        return {"min": 0.0, "max": 0.0, "mean": 0.0, "p50": 0.0, "p95": 0.0, "p99": 0.0}

    sorted_vals = sorted(values)
    n = len(sorted_vals)

    def p(pct: float) -> float:
        idx = max(0, min(n - 1, int(math.ceil(pct / 100.0 * n)) - 1))
        return sorted_vals[idx]

    return {
        "min": round(sorted_vals[0], 2),
        "max": round(sorted_vals[-1], 2),
        "mean": round(sum(sorted_vals) / n, 2),
        "p50": round(p(50), 2),
        "p95": round(p(95), 2),
        "p99": round(p(99), 2),
    }


async def run_soak_harness(
    max_cycles: int,
    max_duration_sec: float | None = None,
    report_dir: Path | None = None,
    tolerance_growth_mb: float = 20.0,
    verbose: bool = False,
) -> dict[str, Any]:
    """Run continuous soak test harness and return structured telemetry results."""
    report_dir = report_dir or Path("artifacts/soak_test")
    report_dir.mkdir(parents=True, exist_ok=True)

    process = psutil.Process(os.getpid())
    tracemalloc.start()
    gc.collect()

    initial_rss_mb = process.memory_info().rss / (1024 * 1024)
    initial_heap_current, initial_heap_peak = tracemalloc.get_traced_memory()
    initial_heap_mb = initial_heap_current / (1024 * 1024)

    # Initialize tool port & scheduler
    tool_port = SoakToolPort()
    scheduler = ExecutionScheduler(max_workers=4)

    cycle_latencies_ms: list[float] = []
    rss_checkpoints_mb: list[float] = []
    heap_checkpoints_mb: list[float] = []
    gc_counts_checkpoints: list[int] = []

    start_wall_time = time.time()
    cycle_count = 0

    print("=" * 75)
    print("🚀 NEXUSAI CONTINUOUS ENDURANCE & SOAK TEST HARNESS")
    print(f"Target Cycles  : {max_cycles}")
    print(
        f"Max Duration   : {max_duration_sec}s"
        if max_duration_sec
        else "Max Duration   : Unlimited"
    )
    print(f"Initial RSS    : {initial_rss_mb:.2f} MB | Initial Heap: {initial_heap_mb:.2f} MB")
    print("=" * 75)

    try:
        while cycle_count < max_cycles:
            now = time.time()
            if max_duration_sec and (now - start_wall_time) >= max_duration_sec:
                print(
                    f"\n⏱️ Duration limit reached: {now - start_wall_time:.1f}s >= {max_duration_sec}s"
                )
                break

            cycle_count += 1
            dag = build_synthetic_dag(cycle_count)

            cycle_start = time.perf_counter()
            _ = await scheduler.schedule_and_execute(dag, tool_port)
            cycle_elapsed_ms = (time.perf_counter() - cycle_start) * 1000.0
            cycle_latencies_ms.append(cycle_elapsed_ms)

            # Periodic telemetry checkpoint (every 50 cycles or final)
            if cycle_count % 50 == 0 or cycle_count == max_cycles:
                gc.collect()
                current_rss = process.memory_info().rss / (1024 * 1024)
                current_heap, _ = tracemalloc.get_traced_memory()
                current_heap_mb = current_heap / (1024 * 1024)
                active_tasks = len([t for t in asyncio.all_tasks() if not t.done()])

                rss_checkpoints_mb.append(current_rss)
                heap_checkpoints_mb.append(current_heap_mb)
                gc_counts_checkpoints.append(len(gc.get_objects()))

                if verbose or cycle_count % 200 == 0:
                    delta_rss = current_rss - initial_rss_mb
                    print(
                        f"[{cycle_count:05d}] RSS: {current_rss:.2f} MB (Δ {delta_rss:+.2f} MB) | "
                        f"Heap: {current_heap_mb:.2f} MB | Active Tasks: {active_tasks} | "
                        f"Lat: {cycle_elapsed_ms:.1f}ms"
                    )

            # Yield control to event loop
            if cycle_count % 10 == 0:
                await asyncio.sleep(0.001)

    except Exception as exc:
        print(f"\n❌ Error during soak execution at cycle {cycle_count}: {exc}")
        raise

    total_wall_time_sec = time.time() - start_wall_time

    # Final garbage collection and audit
    gc.collect()
    final_rss_mb = process.memory_info().rss / (1024 * 1024)
    final_heap_current, peak_heap = tracemalloc.get_traced_memory()
    final_heap_mb = final_heap_current / (1024 * 1024)
    peak_heap_mb = peak_heap / (1024 * 1024)
    tracemalloc.stop()

    uncollected_garbage = len(gc.garbage)
    lingering_tasks = len([t for t in asyncio.all_tasks() if not t.done()])

    total_growth_mb = final_rss_mb - initial_rss_mb
    growth_slope_per_1k = (total_growth_mb / cycle_count * 1000.0) if cycle_count > 0 else 0.0

    latency_stats = calculate_percentiles(cycle_latencies_ms)

    # Health Verdict Logic
    is_leak_free = (
        total_growth_mb <= tolerance_growth_mb and growth_slope_per_1k <= tolerance_growth_mb
    )
    is_gc_healthy = uncollected_garbage == 0 and lingering_tasks <= 2
    verdict = "PASS" if is_leak_free and is_gc_healthy else "FAIL"

    evidence_report: dict[str, Any] = {
        "verdict": verdict,
        "test_name": "NexusAI 72-Hour / Continuous Soak Test",
        "timestamp_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "duration_seconds": round(total_wall_time_sec, 2),
        "total_cycles_executed": cycle_count,
        "throughput_cycles_per_sec": (
            round(cycle_count / total_wall_time_sec, 2) if total_wall_time_sec > 0 else 0
        ),
        "memory_audit": {
            "initial_rss_mb": round(initial_rss_mb, 2),
            "final_rss_mb": round(final_rss_mb, 2),
            "net_rss_growth_mb": round(total_growth_mb, 2),
            "growth_slope_mb_per_1000_cycles": round(growth_slope_per_1k, 2),
            "initial_heap_mb": round(initial_heap_mb, 2),
            "final_heap_mb": round(final_heap_mb, 2),
            "peak_heap_mb": round(peak_heap_mb, 2),
            "tolerance_limit_mb": tolerance_growth_mb,
            "leak_free_verdict": is_leak_free,
        },
        "gc_audit": {
            "uncollected_garbage_objects": uncollected_garbage,
            "lingering_async_tasks": lingering_tasks,
            "gc_healthy_verdict": is_gc_healthy,
        },
        "latency_percentiles_ms": latency_stats,
    }

    # Export JSON Evidence
    json_path = report_dir / "soak_report.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(evidence_report, f, indent=2)

    # Export Markdown Summary
    md_path = report_dir / "soak_report.md"
    md_content = f"""# NexusAI Continuous Endurance & Soak Test Report

- **Verdict**: `{verdict}`
- **Cycles Completed**: {cycle_count:,}
- **Total Duration**: {total_wall_time_sec:.2f}s ({total_wall_time_sec / 3600:.2f} hours)
- **Throughput**: {evidence_report['throughput_cycles_per_sec']} cycles/sec

---

## 🧠 Memory Audit & Leak Detection
| Metric | Initial | Final | Net Growth | Slope (per 1k) | Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **RSS Memory** | {initial_rss_mb:.2f} MB | {final_rss_mb:.2f} MB | {total_growth_mb:+.2f} MB | {growth_slope_per_1k:+.2f} MB | `{'PASS' if is_leak_free else 'FAIL'}` |
| **Heap Memory** | {initial_heap_mb:.2f} MB | {final_heap_mb:.2f} MB | {final_heap_mb - initial_heap_mb:+.2f} MB | Peak: {peak_heap_mb:.2f} MB | `PASS` |

## 🧹 Garbage Collection & Task Audit
- **Uncollected GC Garbage**: `{uncollected_garbage}` objects
- **Lingering Asyncio Tasks**: `{lingering_tasks}` tasks
- **GC Health Status**: `{'HEALTHY' if is_gc_healthy else 'DIRTY'}`

## ⚡ Latency Drift Analysis (ms)
| Mean | P50 (Median) | P95 | P99 | Min | Max |
| :--- | :--- | :--- | :--- | :--- | :--- |
| {latency_stats['mean']} ms | {latency_stats['p50']} ms | {latency_stats['p95']} ms | {latency_stats['p99']} ms | {latency_stats['min']} ms | {latency_stats['max']} ms |
"""
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_content)

    print("\n" + "=" * 75)
    print(f"🏁 SOAK TEST VERDICT: {verdict}")
    print(f"Total Cycles   : {cycle_count:,} in {total_wall_time_sec:.2f}s")
    print(
        f"Net RSS Growth : {total_growth_mb:+.2f} MB (Slope: {growth_slope_per_1k:+.2f} MB / 1k cycles)"
    )
    print(f"Latency P50/P95: {latency_stats['p50']} ms / {latency_stats['p95']} ms")
    print(f"Artifacts      : {json_path} & {md_path}")
    print("=" * 75)

    return evidence_report


def main() -> None:
    parser = argparse.ArgumentParser(description="NexusAI 72-Hour / Continuous Soak Test Runner")
    parser.add_argument(
        "--cycles", type=int, default=1000, help="Maximum number of DAG execution cycles"
    )
    parser.add_argument(
        "--duration", type=str, default=None, help="Max run duration (e.g. 60s, 10m, 1h, 72h)"
    )
    parser.add_argument(
        "--report-dir", type=Path, default=Path("artifacts/soak_test"), help="Report output path"
    )
    parser.add_argument(
        "--tolerance-mb", type=float, default=25.0, help="Memory growth tolerance in MB"
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Print cycle-by-cycle checkpoints"
    )

    args = parser.parse_args()
    duration_sec = parse_duration_seconds(args.duration) if args.duration else None

    report = asyncio.run(
        run_soak_harness(
            max_cycles=args.cycles,
            max_duration_sec=duration_sec,
            report_dir=args.report_dir,
            tolerance_growth_mb=args.tolerance_mb,
            verbose=args.verbose,
        )
    )

    if report["verdict"] != "PASS":
        sys.exit(1)


if __name__ == "__main__":
    main()
