"""Unit tests for Phase 4 P1.8 BenchmarkReport & P1.9 CoverageAnalyzer."""

from __future__ import annotations

from nexusai.brain.eval.benchmark_report import BenchmarkReportAggregator
from nexusai.brain.eval.coverage import CoverageAnalyzer
from nexusai.brain.eval.evaluator import EvaluationResult
from nexusai.brain.eval.golden_dataset import generate_golden_scenario_corpus


def test_coverage_analyzer_on_golden_corpus():
    """Verify CoverageAnalyzer evaluates 100 Golden Scenario Corpus balance and category ratios."""
    corpus = generate_golden_scenario_corpus()
    analyzer = CoverageAnalyzer()

    report = analyzer.analyze(corpus)

    assert report.total_scenarios == 100
    assert report.is_balanced is True
    assert report.category_coverage["TOOL"] == 0.2
    assert report.category_coverage["RECOVERY"] == 0.2
    assert report.category_coverage["PLANNING"] == 0.2
    assert report.category_coverage["REFLECTION"] == 0.2
    assert report.category_coverage["COMPACTION"] == 0.2


def test_benchmark_report_aggregator():
    """Verify BenchmarkReportAggregator aggregates EvaluationResult lists into a BenchmarkReport."""
    corpus = generate_golden_scenario_corpus()
    aggregator = BenchmarkReportAggregator()

    results = [
        EvaluationResult(scenario_id="TOOL-001", success=True, latency_ms=10.0, decision_score=0.9),
        EvaluationResult(
            scenario_id="TOOL-002", success=True, latency_ms=20.0, decision_score=0.95
        ),
        EvaluationResult(
            scenario_id="RECOVERY-021", success=False, latency_ms=30.0, decision_score=0.6
        ),
    ]

    report = aggregator.aggregate(report_id="report-xyz", corpus=corpus, results=results)

    assert report.report_id == "report-xyz"
    assert report.total_scenarios == 3
    assert report.passed_count == 2
    assert report.failed_count == 1
    assert report.pass_rate == round(2 / 3, 4)
    assert report.average_latency_ms == 20.0
    assert "TOOL" in report.category_breakdown
    assert report.category_breakdown["TOOL"]["passed"] == 2
