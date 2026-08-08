"""ReflectionEngine for analyzing expectation-outcome gaps and root cause diagnostics."""

from __future__ import annotations

from dataclasses import dataclass

from nexusai.brain.domain.agent import ExecutionFailure, PlanStep
from nexusai.brain.domain.world import WorldState


@dataclass(frozen=True)
class ReflectionResult:
    """Diagnostic reflection result explaining execution failure root causes and repair actions."""

    expectation_gap: str
    root_cause: str
    repair_suggestion: str
    confidence: float = 0.9
    should_repair_plan: bool = True
    should_update_memory: bool = True


class ReflectionEngine:
    """Analyzes differences between expected step outcome and actual tool failure, producing root cause diagnoses."""

    def reflect_on_failure(
        self,
        step: PlanStep,
        failure: ExecutionFailure,
        world_state: WorldState | None = None,
    ) -> ReflectionResult:
        """Evaluate failure against expectation and generate structured ReflectionResult."""
        exp_gap = f"Expected step {step.step_id} ({step.title}) to complete successfully via {step.tool_name}, but received {failure.reason.value}"

        if failure.reason.name == "TIMEOUT":
            root_cause = "Tool execution exceeded latency budget threshold"
            repair = "FALLBACK_TOOL_OR_INCREASE_TIMEOUT"
        elif failure.reason.name == "MISSING_DEPENDENCY":
            root_cause = "Prerequisite file or tool capability missing from WorldState"
            repair = "INSERT_PREREQUISITE_STEP"
        else:
            root_cause = f"Tool execution failed with error: {failure.error_message}"
            repair = "RETRY_WITH_FALLBACK_ARGUMENTS"

        return ReflectionResult(
            expectation_gap=exp_gap,
            root_cause=root_cause,
            repair_suggestion=repair,
            confidence=0.85,
            should_repair_plan=True,
            should_update_memory=True,
        )
