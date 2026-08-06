"""
Benchmark Metric Collectors for NexusAI.

Each collector returns a BenchmarkResult dataclass containing
the metric name, measured value, and unit for downstream comparison.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent


@dataclass
class BenchmarkResult:
    """Single benchmark metric result."""

    name: str
    value: float
    unit: str
    metadata: dict[str, object] = field(default_factory=dict)


def collect_startup_latency(runs: int = 5) -> BenchmarkResult:
    """Measure median CLI cold-start latency in seconds.

    Args:
        runs: Number of repeat invocations to measure.

    Returns:
        BenchmarkResult with median startup time in seconds.
    """
    python_bin = str(PROJECT_ROOT / ".venv" / "bin" / "python3")
    if not Path(python_bin).exists():
        python_bin = sys.executable

    times: list[float] = []
    for _ in range(runs):
        t0 = time.perf_counter()
        result = subprocess.run(
            [python_bin, "-m", "nexusai.cli.app", "--help"],
            capture_output=True,
            text=True,
            cwd=PROJECT_ROOT,
        )
        t1 = time.perf_counter()
        if result.returncode == 0:
            times.append(t1 - t0)

    times.sort()
    median = times[len(times) // 2] if times else 0.0

    return BenchmarkResult(
        name="startup_time_seconds",
        value=round(median, 4),
        unit="seconds",
        metadata={"runs": runs, "p95": times[int(len(times) * 0.95)] if times else 0.0},
    )


def collect_memory_rss() -> BenchmarkResult:
    """Measure current process RSS memory footprint in MB.

    Returns:
        BenchmarkResult with RSS memory in MB.
    """
    try:
        import psutil  # type: ignore[import]

        process = psutil.Process(os.getpid())
        rss_mb = process.memory_info().rss / (1024 * 1024)
    except ImportError:
        rss_mb = 0.0

    return BenchmarkResult(
        name="memory_rss_mb",
        value=round(rss_mb, 2),
        unit="MB",
    )


def collect_tool_latency(runs: int = 10) -> BenchmarkResult:
    """Measure median tool execution latency in milliseconds.

    This uses subprocess timing as a proxy for tool dispatch overhead
    since we cannot import async runtime in a sync collector context.

    Args:
        runs: Number of repeat iterations to measure.

    Returns:
        BenchmarkResult with median tool latency in milliseconds.
    """
    python_bin = str(PROJECT_ROOT / ".venv" / "bin" / "python3")
    if not Path(python_bin).exists():
        python_bin = sys.executable

    times: list[float] = []
    script = (
        "import asyncio, sys; sys.path.insert(0, 'src'); "
        "from nexusai.tools.workspace.fs import ReadFileTool; "
        "import time; t=time.perf_counter(); "
        "asyncio.run(ReadFileTool().execute(file_path='pyproject.toml')); "
        "print((time.perf_counter()-t)*1000)"
    )
    for _ in range(runs):
        result = subprocess.run(
            [python_bin, "-c", script],
            capture_output=True,
            text=True,
            cwd=PROJECT_ROOT,
        )
        if result.returncode == 0:
            try:
                times.append(float(result.stdout.strip()))
            except ValueError:
                pass

    times.sort()
    median = times[len(times) // 2] if times else 0.0

    return BenchmarkResult(
        name="tool_latency_ms",
        value=round(median, 3),
        unit="ms",
        metadata={"runs": runs, "p95": times[int(len(times) * 0.95)] if times else 0.0},
    )
