"""BenchmarkComparator for comparing cross-implementation BenchmarkReport outputs."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from nexusai.brain.eval.benchmark_report import BenchmarkReport


@dataclass(frozen=True)
class EstimatorQualityMetrics:
    """Domain-specific accuracy metrics for context estimators.

    Attributes:
        mean_absolute_error: MAE of estimated units vs ground truth token count.
        root_mean_squared_error: RMSE of estimated units.
        mean_absolute_percentage_error: MAPE percentage error.
        max_error: Maximum worst-case error encountered.
        p95_error: 95th percentile error.
        p99_error: 99th percentile error.
    """

    mean_absolute_error: float = 0.0
    root_mean_squared_error: float = 0.0
    mean_absolute_percentage_error: float = 0.0
    max_error: float = 0.0
    p95_error: float = 0.0
    p99_error: float = 0.0


@dataclass(frozen=True)
class SummarizerQualityMetrics:
    """Domain-specific quality metrics for summary generators.

    Attributes:
        compression_ratio: Ratio of summary length vs original observation payload length.
        information_retention_ratio: Ratio of retained key information points.
        keyword_recall: Ratio of preserved technical keywords.
        faithfulness_score: Hallucination resistance quality score (0.0 to 1.0).
    """

    compression_ratio: float = 0.0
    information_retention_ratio: float = 0.0
    keyword_recall: float = 0.0
    faithfulness_score: float = 1.0


@dataclass(frozen=True)
class ComparisonReport:
    """Structured report output comparing two implementation BenchmarkReport runs.

    Attributes:
        comparison_id: Unique comparison UUID string.
        baseline_name: Baseline implementation name (e.g. "CharacterEstimator").
        candidate_name: Candidate implementation name (e.g. "ProviderTokenizerEstimator").
        winner_by_latency: Name of implementation with lowest average latency.
        winner_by_score: Name of implementation with highest decision quality score.
        latency_delta_ms: Mean latency difference in ms (candidate - baseline).
        score_delta: Decision score difference (candidate - baseline).
        recommendation: Human-readable technical recommendation string.
        estimator_metrics: Optional EstimatorQualityMetrics for token estimators.
        summarizer_metrics: Optional SummarizerQualityMetrics for summary generators.
    """

    comparison_id: str
    baseline_name: str
    candidate_name: str
    winner_by_latency: str
    winner_by_score: str
    latency_delta_ms: float
    score_delta: float
    recommendation: str
    estimator_metrics: EstimatorQualityMetrics = field(default_factory=EstimatorQualityMetrics)
    summarizer_metrics: SummarizerQualityMetrics = field(default_factory=SummarizerQualityMetrics)

    def save_json(self, file_path: Path | str) -> None:
        """Save ComparisonReport to JSON file."""
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")


@dataclass(frozen=True)
class MultiComparisonReport:
    """Multi-candidate comparison report ranking multiple implementations.

    Attributes:
        comparison_id: Unique comparison UUID string.
        candidate_names: Tuple of evaluated candidate implementation names.
        rankings: Tuple of candidate rankings sorted by overall performance.
        overall_winner: Overall winning implementation name.
    """

    comparison_id: str
    candidate_names: tuple[str, ...] = ()
    rankings: tuple[dict[str, Any], ...] = ()
    overall_winner: str = ""

    def save_json(self, file_path: Path | str) -> None:
        """Save MultiComparisonReport to JSON file."""
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")


class BenchmarkComparator:
    """Compares implementation BenchmarkReport outputs and generates structured ComparisonReports."""

    def compare(
        self,
        comparison_id: str,
        baseline_name: str,
        baseline_report: BenchmarkReport,
        candidate_name: str,
        candidate_report: BenchmarkReport,
        estimator_metrics: EstimatorQualityMetrics | None = None,
        summarizer_metrics: SummarizerQualityMetrics | None = None,
    ) -> ComparisonReport:
        """Compare baseline and candidate BenchmarkReports."""
        latency_delta = round(
            candidate_report.average_latency_ms - baseline_report.average_latency_ms, 2
        )
        score_delta = round(
            candidate_report.average_decision_score - baseline_report.average_decision_score, 2
        )

        winner_latency = (
            baseline_name
            if baseline_report.average_latency_ms <= candidate_report.average_latency_ms
            else candidate_name
        )
        winner_score = (
            baseline_name
            if baseline_report.average_decision_score >= candidate_report.average_decision_score
            else candidate_name
        )

        if (
            candidate_report.average_decision_score > baseline_report.average_decision_score
            and latency_delta <= 5.0
        ):
            rec = f"Promote candidate '{candidate_name}': higher quality score (+{score_delta:.2f}) with acceptable latency delta ({latency_delta:+.2f} ms)."
        elif (
            baseline_report.average_latency_ms < candidate_report.average_latency_ms
            and score_delta == 0.0
        ):
            rec = f"Retain baseline '{baseline_name}': faster execution ({latency_delta:+.2f} ms latency overhead in candidate) with identical quality."
        else:
            rec = f"Tradeoff detected between '{baseline_name}' and '{candidate_name}': score delta = {score_delta:+.2f}, latency delta = {latency_delta:+.2f} ms."

        return ComparisonReport(
            comparison_id=comparison_id,
            baseline_name=baseline_name,
            candidate_name=candidate_name,
            winner_by_latency=winner_latency,
            winner_by_score=winner_score,
            latency_delta_ms=latency_delta,
            score_delta=score_delta,
            recommendation=rec,
            estimator_metrics=estimator_metrics or EstimatorQualityMetrics(),
            summarizer_metrics=summarizer_metrics or SummarizerQualityMetrics(),
        )

    def compare_many(
        self,
        comparison_id: str,
        reports: dict[str, BenchmarkReport],
    ) -> MultiComparisonReport:
        """Compare multiple candidate BenchmarkReports and generate a ranked MultiComparisonReport."""
        items: list[dict[str, Any]] = []
        for name, rep in reports.items():
            items.append(
                {
                    "name": name,
                    "pass_rate": rep.pass_rate,
                    "latency_ms": rep.average_latency_ms,
                    "decision_score": rep.average_decision_score,
                }
            )

        # Sort by pass_rate desc, decision_score desc, latency_ms asc
        items.sort(key=lambda x: (-x["pass_rate"], -x["decision_score"], x["latency_ms"]))

        for rank, item in enumerate(items, 1):
            item["rank"] = rank

        winner = items[0]["name"] if items else "NONE"

        return MultiComparisonReport(
            comparison_id=comparison_id,
            candidate_names=tuple(reports.keys()),
            rankings=tuple(items),
            overall_winner=winner,
        )
