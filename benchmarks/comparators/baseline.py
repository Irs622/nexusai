"""
Benchmark Baseline Comparator for NexusAI.

Loads the most recent baseline JSON, compares collected metrics,
computes percentage delta, and determines regression status.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from benchmarks.collectors.metrics import BenchmarkResult

BASELINE_DIR = Path(__file__).parent.parent / "history" / "baseline"
RUNS_DIR = Path(__file__).parent.parent / "history" / "runs"


@dataclass
class ComparisonResult:
    """Result of comparing a collected metric against baseline."""

    name: str
    current: float
    baseline_median: float
    baseline_p95: float
    max_threshold: float
    delta_pct: float
    passed: bool
    unit: str


def _load_latest_baseline() -> dict[str, object]:
    """Load the most recent baseline JSON file.

    Returns:
        Parsed baseline JSON dict.

    Raises:
        FileNotFoundError: If no baseline file exists.
    """
    baseline_files = sorted(BASELINE_DIR.glob("*.json"), reverse=True)
    if not baseline_files:
        raise FileNotFoundError(
            f"No baseline files found in {BASELINE_DIR}. "
            "Run benchmarks and commit a baseline first."
        )
    return json.loads(baseline_files[0].read_text())  # type: ignore[return-value]


def compare_results(results: list[BenchmarkResult]) -> list[ComparisonResult]:
    """Compare collected results against the latest baseline.

    Args:
        results: List of BenchmarkResult objects from collectors.

    Returns:
        List of ComparisonResult objects with delta and pass/fail status.
    """
    baseline_data = _load_latest_baseline()
    metrics_baseline: dict[str, dict[str, float]] = baseline_data.get("metrics", {})  # type: ignore[assignment]

    comparisons: list[ComparisonResult] = []

    for result in results:
        metric_name = result.name
        if metric_name not in metrics_baseline:
            continue

        b = metrics_baseline[metric_name]
        baseline_median: float = b.get("median", 0.0)
        baseline_p95: float = b.get("p95", 0.0)
        max_threshold: float = b.get("max_threshold", float("inf"))

        current = result.value
        delta_pct = (
            ((current - baseline_median) / baseline_median * 100)
            if baseline_median > 0
            else 0.0
        )
        passed = current <= max_threshold

        comparisons.append(
            ComparisonResult(
                name=metric_name,
                current=current,
                baseline_median=baseline_median,
                baseline_p95=baseline_p95,
                max_threshold=max_threshold,
                delta_pct=round(delta_pct, 2),
                passed=passed,
                unit=result.unit,
            )
        )

    return comparisons
