"""Agent Evaluation sub-package for NexusAI Agent Runtime."""

from nexusai.brain.eval.benchmark_report import (
    BenchmarkEnvironment,
    BenchmarkReport,
    BenchmarkReportAggregator,
    RegressionReport,
)
from nexusai.brain.eval.comparator import (
    BenchmarkComparator,
    ComparisonReport,
    MultiComparisonReport,
)
from nexusai.brain.eval.coverage import CoverageAnalyzer, CoverageReport
from nexusai.brain.eval.decision_dataset import DecisionDataset, DecisionDatasetEntry
from nexusai.brain.eval.evaluator import AgentEvaluator, EvaluationResult
from nexusai.brain.eval.golden_dataset import generate_golden_scenario_corpus
from nexusai.brain.eval.learning import EvaluationSummary, OfflineEvaluator, StrategyTrainer
from nexusai.brain.eval.runner import ScenarioRunner
from nexusai.brain.eval.scenario import Scenario, ScenarioCorpus

__all__ = [
    "AgentEvaluator",
    "BenchmarkComparator",
    "BenchmarkEnvironment",
    "BenchmarkReport",
    "BenchmarkReportAggregator",
    "ComparisonReport",
    "CoverageAnalyzer",
    "CoverageReport",
    "DecisionDataset",
    "DecisionDatasetEntry",
    "EvaluationResult",
    "EvaluationSummary",
    "MultiComparisonReport",
    "OfflineEvaluator",
    "RegressionReport",
    "Scenario",
    "ScenarioCorpus",
    "ScenarioRunner",
    "StrategyTrainer",
    "generate_golden_scenario_corpus",
]
