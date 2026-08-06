"""
Benchmark Trend Reporter for NexusAI.

Renders rich terminal output for benchmark comparison results:
  Metric         | Current | Previous | Delta   | Status
  ---------------------------------------------------------------
  startup_time_s | 1.48s   | 1.54s    | -3.90%  | ✅ PASS
  memory_rss_mb  | 148.2MB | 145.2MB  | +2.07%  | ✅ PASS
  tool_latency_ms| 13.2ms  | 12.4ms   | +6.45%  | ✅ PASS
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from benchmarks.comparators.baseline import ComparisonResult

RUNS_DIR = Path(__file__).parent.parent / "history" / "runs"

COL_WIDTH = {
    "metric": 22,
    "current": 12,
    "previous": 12,
    "delta": 10,
    "threshold": 14,
    "status": 8,
}

SEP = "─"


def _status_icon(passed: bool) -> str:
    return "✅ PASS" if passed else "❌ FAIL"


def _delta_str(delta: float) -> str:
    prefix = "+" if delta >= 0 else ""
    return f"{prefix}{delta:.2f}%"


def print_trend_report(comparisons: list[ComparisonResult]) -> bool:
    """Print a rich terminal trend report.

    Args:
        comparisons: List of ComparisonResult objects from comparator.

    Returns:
        True if all comparisons passed, False otherwise.
    """
    total_width = sum(COL_WIDTH.values()) + len(COL_WIDTH) * 3 + 1

    print("\n" + "=" * total_width)
    print("  NexusAI Benchmark Quality Gate — Trend Report")
    print("=" * total_width)

    header = (
        f"  {'Metric':<{COL_WIDTH['metric']}}"
        f"{'Current':<{COL_WIDTH['current']}}"
        f"{'Previous':<{COL_WIDTH['previous']}}"
        f"{'Delta':<{COL_WIDTH['delta']}}"
        f"{'Threshold':<{COL_WIDTH['threshold']}}"
        f"{'Status':<{COL_WIDTH['status']}}"
    )
    print(header)
    print("  " + SEP * (total_width - 2))

    all_passed = True
    for c in comparisons:
        current_str = f"{c.current:.3f}{c.unit}"
        previous_str = f"{c.baseline_median:.3f}{c.unit}"
        threshold_str = f"<= {c.max_threshold:.1f}{c.unit}"
        delta_str = _delta_str(c.delta_pct)
        status_str = _status_icon(c.passed)

        if not c.passed:
            all_passed = False

        row = (
            f"  {c.name:<{COL_WIDTH['metric']}}"
            f"{current_str:<{COL_WIDTH['current']}}"
            f"{previous_str:<{COL_WIDTH['previous']}}"
            f"{delta_str:<{COL_WIDTH['delta']}}"
            f"{threshold_str:<{COL_WIDTH['threshold']}}"
            f"{status_str:<{COL_WIDTH['status']}}"
        )
        print(row)

    print("  " + SEP * (total_width - 2))
    overall = "✅ ALL BENCHMARKS PASSED" if all_passed else "❌ BENCHMARK REGRESSION DETECTED"
    print(f"\n  {overall}\n")
    print("=" * total_width + "\n")

    return all_passed


def save_run_snapshot(comparisons: list[ComparisonResult]) -> Path:
    """Save the current benchmark run to history/runs/<date>.json.

    Args:
        comparisons: List of ComparisonResult objects.

    Returns:
        Path to the saved run snapshot file.
    """
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    run_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    snapshot_path = RUNS_DIR / f"{run_date}.json"

    snapshot: dict[str, object] = {
        "date": run_date,
        "passed": all(c.passed for c in comparisons),
        "metrics": {
            c.name: {
                "current": c.current,
                "baseline_median": c.baseline_median,
                "delta_pct": c.delta_pct,
                "max_threshold": c.max_threshold,
                "passed": c.passed,
                "unit": c.unit,
            }
            for c in comparisons
        },
    }

    snapshot_path.write_text(json.dumps(snapshot, indent=2))
    return snapshot_path
