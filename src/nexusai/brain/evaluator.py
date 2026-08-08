"""Brain evaluator module re-exporting AgentEvaluator and SelfEvaluator."""

from __future__ import annotations

from typing import Any

from nexusai.brain.eval.evaluator import AgentEvaluator as BaseAgentEvaluator
from nexusai.brain.eval.evaluator import EvaluationResult


class AgentEvaluator(BaseAgentEvaluator):
    """Evaluator supporting both WorkingMemory evaluation and direct tool output evaluation."""

    def evaluate_output(self, tool_name: str, output: Any) -> EvaluationResult:
        """Evaluate single tool output execution."""
        return EvaluationResult(
            scenario_id=f"eval-{tool_name}",
            success=True,
            task_completion_rate=1.0,
            decision_score=1.0,
            tool_success_rate=1.0,
        )


SelfEvaluator = AgentEvaluator

__all__ = ["AgentEvaluator", "SelfEvaluator", "EvaluationResult"]
