"""OfflineEvaluator and StrategyTrainer closing the learning loop with DecisionDataset."""

from __future__ import annotations

from dataclasses import dataclass

from nexusai.brain.domain.agent import PlannerWeights
from nexusai.brain.eval.decision_dataset import DecisionDataset


@dataclass(frozen=True)
class EvaluationSummary:
    """Summary metrics produced by OfflineEvaluator."""

    total_decisions: int
    win_rate: float
    mean_latency_ms: float
    mean_reward: float


class OfflineEvaluator:
    """Evaluates historical DecisionDataset entries to compute performance metrics."""

    def evaluate_dataset(self, dataset: DecisionDataset) -> EvaluationSummary:
        """Calculate total decisions, win rate, mean latency, and mean scalar reward."""
        if not dataset.entries:
            return EvaluationSummary(
                total_decisions=0, win_rate=0.0, mean_latency_ms=0.0, mean_reward=0.0
            )

        total = len(dataset.entries)
        wins = sum(1 for e in dataset.entries if e.outcome_success)
        total_latency = sum(e.execution_latency_ms for e in dataset.entries)
        total_reward = sum(e.reward for e in dataset.entries)

        return EvaluationSummary(
            total_decisions=total,
            win_rate=wins / total,
            mean_latency_ms=total_latency / total,
            mean_reward=total_reward / total,
        )


class StrategyTrainer:
    """Tunes PlannerWeights based on historical DecisionDataset feedback to close the learning loop."""

    def tune_weights(
        self, summary: EvaluationSummary, current_weights: PlannerWeights
    ) -> PlannerWeights:
        """Adjust success_weight and latency_weight dynamically based on dataset win rate and latency."""
        if summary.win_rate < 0.8:
            # Increase success weight if win rate is low
            new_success = min(0.70, current_weights.success_weight + 0.05)
            new_latency = max(0.05, current_weights.latency_weight - 0.05)
        else:
            # Optimize for latency if win rate is high
            new_success = max(0.35, current_weights.success_weight - 0.02)
            new_latency = min(0.25, current_weights.latency_weight + 0.02)

        return PlannerWeights(
            success_weight=round(new_success, 2),
            info_weight=current_weights.info_weight,
            latency_weight=round(new_latency, 2),
            cost_weight=current_weights.cost_weight,
        )
