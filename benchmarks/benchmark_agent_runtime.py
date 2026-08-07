"""Reproducible Benchmark Suite for NexusAI Agent Runtime (LoopExecutor & Pipeline).

Measures loop execution latency (mean, median, P95, P99), cold vs warm start, throughput, memory allocations,
and captures full environment metadata (Python version, OS/platform, CPU architecture, git commit hash, timestamp).
"""

from __future__ import annotations

import asyncio
import platform
import statistics
import subprocess
import sys
import time
import tracemalloc
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from nexusai.brain.builder import AgentRuntimeBuilder
from nexusai.brain.domain.agent import AgentGoal
from nexusai.brain.domain.session import BrainSession
from nexusai.brain.runtime.state import SessionState
from nexusai.tools.adapter import ToolRegistryAdapter
from nexusai.tools.registry import ToolRegistry


class BenchmarkMockTool:
    """Fast, deterministic mock tool for runtime latency benchmark measurements."""

    name = "benchmark_mock_tool"
    description = "Benchmark test tool"

    def execute(self, **kwargs: str) -> str:
        return "benchmark_result_ok"


def _get_git_commit_hash() -> str:
    """Retrieve active git commit hash or fallback string."""
    try:
        res = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        )
        return res.stdout.strip()
    except Exception:
        return "unknown_commit"


def get_environment_metadata() -> dict[str, str]:
    """Capture full environment metadata for reproducible benchmark auditing."""
    return {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "python_version": sys.version.split()[0],
        "platform": platform.platform(),
        "processor": platform.processor() or platform.machine(),
        "commit_hash": _get_git_commit_hash(),
    }


async def run_benchmark(num_iterations: int = 1000) -> dict[str, Any]:
    """Execute reproducible benchmark suite over num_iterations runs."""
    registry = ToolRegistry()
    registry.register(BenchmarkMockTool())
    tool_port = ToolRegistryAdapter(registry)

    facade = (
        AgentRuntimeBuilder()
        .with_tool_port(tool_port)
        .build()
    )

    session = BrainSession(session_id=uuid4(), conversation_id=uuid4())
    goal = AgentGoal(description="Benchmark goal task")
    state = SessionState(provider_id="mock", active_model="mock-v1")

    # Warm-up run / Cold start measurement
    tracemalloc.start()
    t0 = time.perf_counter()
    cold_response = await facade.run_agent_session(session, goal, state)
    cold_duration_ms = (time.perf_counter() - t0) * 1000.0
    _, peak_mem_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    durations: list[float] = []

    # Warm runs benchmark loop
    tracemalloc.start()
    for _ in range(num_iterations):
        t_start = time.perf_counter()
        resp = await facade.run_agent_session(session, goal, state)
        t_elapsed = (time.perf_counter() - t_start) * 1000.0
        durations.append(t_elapsed)

    current_mem_bytes, peak_warm_mem_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    durations_sorted = sorted(durations)
    mean_ms = statistics.mean(durations)
    median_ms = statistics.median(durations)
    p95_ms = durations_sorted[int(num_iterations * 0.95)]
    p99_ms = durations_sorted[int(num_iterations * 0.99)]

    report: dict[str, Any] = {
        "environment": get_environment_metadata(),
        "metrics": {
            "num_iterations": num_iterations,
            "cold_start_ms": round(cold_duration_ms, 3),
            "mean_latency_ms": round(mean_ms, 3),
            "median_latency_ms": round(median_ms, 3),
            "p95_latency_ms": round(p95_ms, 3),
            "p99_latency_ms": round(p99_ms, 3),
            "peak_cold_mem_kb": round(peak_mem_bytes / 1024.0, 2),
            "peak_warm_mem_kb": round(peak_warm_mem_bytes / 1024.0, 2),
            "iterations_per_second": round(1000.0 / mean_ms, 1),
        },
    }

    return report


if __name__ == "__main__":
    print("=" * 60)
    print("RUNNING REPRODUCIBLE AGENT RUNTIME BENCHMARK SUITE")
    print("=" * 60)
    results = asyncio.run(run_benchmark(num_iterations=1000))
    print("ENVIRONMENT METADATA:")
    for k, v in results["environment"].items():
        print(f"  {k:20s}: {v}")
    print("\nBENCHMARK METRICS:")
    for k, v in results["metrics"].items():
        print(f"  {k:20s}: {v}")
    print("=" * 60)
    print("BENCHMARK COMPLETED SUCCESSFULLY!")
