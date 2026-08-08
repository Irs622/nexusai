#!/usr/bin/env python3
"""NexusAI Continuous Benchmarking CLI Tool for CI/CD Pipelines.

Executes the 100 Golden Scenario Dataset suite, calculates BenchmarkReport metrics,
generates coverage analysis, dumps structured CI JSON artifacts (benchmark.json,
comparison.json, coverage.json, trend.json), and exits with 0 (PASS) or 1 (FAIL).
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from nexusai.brain.compaction.budget import CharacterEstimator
from nexusai.brain.container import RuntimeDependencies
from nexusai.brain.eval.benchmark_report import BenchmarkReportAggregator
from nexusai.brain.eval.coverage import CoverageAnalyzer
from nexusai.brain.eval.golden_dataset import generate_golden_scenario_corpus
from nexusai.brain.eval.runner import ScenarioRunner


async def main() -> int:
    """Execute CI/CD Continuous Benchmark Suite."""
    print("=" * 70)
    print("NexusAI Continuous Benchmarking CI/CD Suite")
    print("=" * 70)

    corpus = generate_golden_scenario_corpus()
    print(f"Loaded Golden Corpus: '{corpus.corpus_name}' (Version {corpus.version}, {len(corpus.scenarios)} scenarios)")

    # 1. Coverage Analysis
    analyzer = CoverageAnalyzer()
    coverage_report = analyzer.analyze(corpus)
    coverage_file = Path("artifacts/ci/coverage.json")
    coverage_report.save_json(coverage_file)
    print(f"Coverage Report saved to '{coverage_file}' (Balanced: {coverage_report.is_balanced})")

    # 2. Run Benchmark
    deps = RuntimeDependencies(context_estimator=CharacterEstimator())
    runner = ScenarioRunner(deps=deps)

    print("Executing 100 Golden Scenarios...")
    results = await runner.run_corpus(corpus)

    aggregator = BenchmarkReportAggregator()
    report = aggregator.aggregate(report_id="ci-run-latest", corpus=corpus, results=results)
    benchmark_file = Path("artifacts/ci/benchmark.json")
    report.save_json(benchmark_file)
    print(f"Benchmark Report saved to '{benchmark_file}'")

    print("\n" + "-" * 70)
    print("CI Benchmark Summary:")
    print(f"Total Scenarios Evaluated : {report.total_scenarios}")
    print(f"Passed Scenarios          : {report.passed_count}")
    print(f"Failed Scenarios          : {report.failed_count}")
    print(f"Pass Rate                 : {report.pass_rate * 100:.2f}%")
    print(f"Average Turn Latency      : {report.average_latency_ms:.2f} ms")
    print(f"P95 Turn Latency          : {report.p95_latency_ms:.2f} ms")
    print(f"Average Decision Score    : {report.average_decision_score:.2f}")
    print(f"Environment Platform      : {report.environment.operating_system} ({report.environment.architecture})")
    print("-" * 70)

    if report.pass_rate < 1.0:
        print("\n❌ CI BENCHMARK FAILED: Pass rate lower than 100% threshold!")
        return 1

    print("\n✅ CI BENCHMARK PASSED SUCCESSFULLY! All 100 Golden Scenarios Passed 100%.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
