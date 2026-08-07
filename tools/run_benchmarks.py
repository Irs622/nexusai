"""
Modular Benchmark Runner for NexusAI.

Orchestrates the full benchmark pipeline:
  1. Collect metrics (startup, memory RSS, tool latency)
  2. Compare against latest baseline (benchmarks/history/baseline/)
  3. Generate rich terminal trend report
  4. Save run snapshot to benchmarks/history/runs/<date>.json
  5. Exit with non-zero if any threshold is exceeded.
"""

import sys
import argparse
from pathlib import Path



from benchmarks.collectors.metrics import (
    collect_memory_rss,
    collect_startup_latency,
    collect_tool_latency,
)
from benchmarks.comparators.baseline import compare_results
from benchmarks.reporters.terminal import print_trend_report, save_run_snapshot


def run_benchmarks(quick: bool = False, save: bool = True) -> int:
    """Run the full NexusAI benchmark pipeline.

    Args:
        quick: If True, use fewer iterations for faster CI runs.
        save: If True, persist the run snapshot to history/runs/.

    Returns:
        0 if all benchmarks pass, 1 if any regression is detected.
    """
    runs = 3 if quick else 5
    tool_runs = 5 if quick else 10

    print("=== [Benchmark Pipeline] NexusAI Performance Quality Gate ===\n")
    print("Collecting metrics...")

    results = [
        collect_startup_latency(runs=runs),
        collect_memory_rss(),
        collect_tool_latency(runs=tool_runs),
    ]

    for r in results:
        print(f"  Collected {r.name}: {r.value} {r.unit}")

    print("\nComparing against baseline...")
    try:
        comparisons = compare_results(results)
    except FileNotFoundError as e:
        print(f"❌ Benchmark baseline not found: {e}")
        return 1

    all_passed = print_trend_report(comparisons)

    if save and comparisons:
        snapshot_path = save_run_snapshot(comparisons)
        print(f"  Run snapshot saved: {snapshot_path.relative_to(Path(__file__).parent.parent)}")

    return 0 if all_passed else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NexusAI Benchmark Runner")
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Use fewer iterations (for faster CI runs)",
    )
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="Skip saving run snapshot to history/runs/",
    )
    args = parser.parse_args()
    sys.exit(run_benchmarks(quick=args.quick, save=not args.no_save))
