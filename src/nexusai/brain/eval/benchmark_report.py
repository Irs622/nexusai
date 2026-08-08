"""BenchmarkReport dataclass and aggregator for scenario evaluation suites."""

from __future__ import annotations

import json
import os
import platform
import statistics
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from nexusai.brain.eval.evaluator import EvaluationResult
from nexusai.brain.eval.scenario import ScenarioCorpus


@dataclass(frozen=True)
class BenchmarkEnvironment:
    """Captured runtime execution environment metadata for benchmark reproducibility.

    Attributes:
        python_version: Python runtime version string.
        operating_system: OS platform string (e.g. Darwin, Linux).
        architecture: Machine architecture string (e.g. arm64, x86_64).
        cpu_count: Number of CPU cores available.
        git_commit: Current git commit SHA string (default "HEAD").
        git_branch: Current git branch name string (default "main").
        dataset_hash: SHA-256 hash of evaluated ScenarioCorpus.
        provider_version: Vendor LLM provider version string.
        model_version: Active model identifier version string.
        benchmark_version: Benchmark framework version string.
    """

    python_version: str = field(default_factory=platform.python_version)
    operating_system: str = field(default_factory=platform.system)
    architecture: str = field(default_factory=platform.machine)
    cpu_count: int = field(default_factory=lambda: os.cpu_count() or 1)
    git_commit: str = "HEAD"
    git_branch: str = "main"
    dataset_hash: str = ""
    provider_version: str = "v1.0"
    model_version: str = "mock-v1"
    benchmark_version: str = "1.0"


@dataclass(frozen=True)
class BenchmarkReport:
    """Aggregated benchmark evaluation report summarizing corpus execution quality metrics.

    Attributes:
        report_id: Unique benchmark report UUID string.
        corpus_name: Evaluated scenario corpus name string.
        corpus_version: Evaluated scenario corpus dataset version integer.
        total_scenarios: Total number of scenarios evaluated.
        passed_count: Count of successful scenarios passing evaluation gates.
        failed_count: Count of failed scenarios.
        pass_rate: Ratio of passed scenarios vs total scenarios (0.0 to 1.0).
        average_latency_ms: Mean scenario execution latency in milliseconds.
        p95_latency_ms: 95th percentile scenario execution latency in milliseconds.
        average_decision_score: Mean agent decision quality score.
        failure_distribution: Frequency map of failure category counts.
        category_breakdown: Granular breakdown map per category (TOOL, RECOVERY, PLANNING, REFLECTION, COMPACTION).
        environment: BenchmarkEnvironment metadata object.
        timestamp: Epoch timestamp float when report was generated.
    """

    report_id: str
    corpus_name: str
    corpus_version: int = 1
    total_scenarios: int = 0
    passed_count: int = 0
    failed_count: int = 0
    pass_rate: float = 0.0
    average_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    average_decision_score: float = 0.0
    failure_distribution: dict[str, int] = field(default_factory=dict)
    category_breakdown: dict[str, dict[str, Any]] = field(default_factory=dict)
    environment: BenchmarkEnvironment = field(default_factory=BenchmarkEnvironment)
    timestamp: float = field(default_factory=time.time)

    def save_json(self, file_path: Path | str) -> None:
        """Save BenchmarkReport to JSON file."""
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")


@dataclass(frozen=True)
class RegressionReport:
    """Regression comparison report comparing candidate BenchmarkReport against baseline BenchmarkReport.

    Attributes:
        baseline_id: Baseline report UUID string.
        candidate_id: Candidate report UUID string.
        pass_rate_delta: Difference in pass rate (candidate - baseline).
        latency_delta_ms: Difference in mean latency in ms (candidate - baseline).
        p95_latency_delta_ms: Difference in P95 latency in ms.
        decision_score_delta: Difference in decision score.
        has_regression: Boolean flag indicating detected performance regression.
        regression_reasons: Tuple of detected regression warning strings.
        regression_cause: Root-cause diagnosis string.
        history: Tuple of historical BenchmarkReport snapshots for multi-version trend analysis.
    """

    baseline_id: str
    candidate_id: str
    pass_rate_delta: float = 0.0
    latency_delta_ms: float = 0.0
    p95_latency_delta_ms: float = 0.0
    decision_score_delta: float = 0.0
    has_regression: bool = False
    regression_reasons: tuple[str, ...] = ()
    regression_cause: str = ""
    history: tuple[BenchmarkReport, ...] = ()

    def save_json(self, file_path: Path | str) -> None:
        """Save RegressionReport to JSON file."""
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")


class BenchmarkReportAggregator:
    """Aggregates individual EvaluationResult reports into a comprehensive BenchmarkReport."""

    def aggregate(
        self,
        report_id: str,
        corpus: ScenarioCorpus,
        results: list[EvaluationResult],
    ) -> BenchmarkReport:
        """Aggregate EvaluationResult list into a structured BenchmarkReport."""
        total = len(results)
        if total == 0:
            return BenchmarkReport(
                report_id=report_id,
                corpus_name=corpus.corpus_name,
                corpus_version=corpus.version,
            )

        passed = sum(1 for r in results if r.success)
        failed = total - passed
        pass_rate = passed / total

        latencies = [r.latency_ms for r in results]
        avg_latency = statistics.mean(latencies)
        sorted_latencies = sorted(latencies)
        p95_idx = min(int(0.95 * total), total - 1)
        p95_latency = sorted_latencies[p95_idx]

        avg_score = statistics.mean([r.decision_score for r in results])

        # Failure distribution
        failures: dict[str, int] = {}
        for r in results:
            if not r.success:
                reason = (
                    "STATE_HASH_MISMATCH"
                    if r.expected_state_hash and r.expected_state_hash != r.actual_state_hash
                    else "TASK_INCOMPLETE"
                )
                failures[reason] = failures.get(reason, 0) + 1

        # Category breakdown map scenario_id -> scenario category
        scenario_map = {s.scenario_id: s for s in corpus.scenarios}
        cat_map: dict[str, list[EvaluationResult]] = {}
        for r in results:
            sc = scenario_map.get(r.scenario_id)
            cat = sc.category if sc else "UNKNOWN"
            if cat not in cat_map:
                cat_map[cat] = []
            cat_map[cat].append(r)

        category_breakdown: dict[str, dict[str, Any]] = {}
        for cat, cat_res in cat_map.items():
            cat_total = len(cat_res)
            cat_passed = sum(1 for cr in cat_res if cr.success)
            category_breakdown[cat] = {
                "total": cat_total,
                "passed": cat_passed,
                "pass_rate": round(cat_passed / max(1, cat_total), 2),
                "average_latency_ms": round(statistics.mean([cr.latency_ms for cr in cat_res]), 2),
                "average_decision_score": round(
                    statistics.mean([cr.decision_score for cr in cat_res]), 2
                ),
            }

        return BenchmarkReport(
            report_id=report_id,
            corpus_name=corpus.corpus_name,
            corpus_version=corpus.version,
            total_scenarios=total,
            passed_count=passed,
            failed_count=failed,
            pass_rate=round(pass_rate, 4),
            average_latency_ms=round(avg_latency, 2),
            p95_latency_ms=round(p95_latency, 2),
            average_decision_score=round(avg_score, 2),
            failure_distribution=failures,
            category_breakdown=category_breakdown,
            environment=BenchmarkEnvironment(dataset_hash=f"hash-{len(corpus.scenarios)}"),
        )

    def compare_regression(
        self,
        baseline: BenchmarkReport,
        candidate: BenchmarkReport,
        history: list[BenchmarkReport] | None = None,
    ) -> RegressionReport:
        """Compare candidate BenchmarkReport against baseline to generate a RegressionReport."""
        pass_rate_delta = candidate.pass_rate - baseline.pass_rate
        latency_delta = candidate.average_latency_ms - baseline.average_latency_ms
        p95_delta = candidate.p95_latency_ms - baseline.p95_latency_ms
        score_delta = candidate.average_decision_score - baseline.average_decision_score

        reasons: list[str] = []
        if pass_rate_delta < -0.01:
            reasons.append(f"Pass rate regressed by {abs(pass_rate_delta)*100:.2f}%")
        if latency_delta > 15.0:
            reasons.append(f"Average latency increased by {latency_delta:.2f} ms")
        if score_delta < -0.05:
            reasons.append(f"Decision quality score regressed by {abs(score_delta):.2f}")

        cause = "; ".join(reasons) if reasons else "No regression detected"
        hist_tuple = tuple(history) if history else (baseline, candidate)

        return RegressionReport(
            baseline_id=baseline.report_id,
            candidate_id=candidate.report_id,
            pass_rate_delta=round(pass_rate_delta, 4),
            latency_delta_ms=round(latency_delta, 2),
            p95_latency_delta_ms=round(p95_delta, 2),
            decision_score_delta=round(score_delta, 2),
            has_regression=len(reasons) > 0,
            regression_reasons=tuple(reasons),
            regression_cause=cause,
            history=hist_tuple,
        )
