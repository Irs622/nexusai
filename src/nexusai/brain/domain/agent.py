"""Domain entities and contracts for multi-turn Agent Runtime."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import UUID, uuid4


class StepStatus(str, Enum):
    """Execution status of an individual plan step."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class LoopDecision(str, Enum):
    """Actionable state decisions produced by IDecisionStrategy."""

    CONTINUE = "CONTINUE"
    REPLAN = "REPLAN"
    COMPLETE = "COMPLETE"
    FAIL = "FAIL"


@dataclass(frozen=True)
class AgentGoal:
    """Canonical goal definition provided to Agent Runtime.

    Attributes:
        goal_id: Unique UUID identifier.
        description: High-level natural language description of goal.
        constraints: Optional list of execution constraints.
    """

    description: str
    goal_id: UUID = field(default_factory=uuid4)
    constraints: list[str] = field(default_factory=list)


@dataclass
class PlanStep:
    """Individual executable step within an AgentPlan.

    Attributes:
        step_id: 1-indexed numeric step identifier.
        title: Short title of the step.
        description: Detailed execution description.
        tool_name: Optional tool to execute.
        arguments: Tool invocation arguments dictionary.
        status: Step execution status.
    """

    step_id: int
    title: str
    description: str
    tool_name: str | None = None
    arguments: dict[str, Any] = field(default_factory=dict)
    status: StepStatus = StepStatus.PENDING


@dataclass(frozen=True)
class FailureRecord:
    """Failure record documenting an execution error.

    Attributes:
        step_id: Failed step ID.
        error_message: Detailed error string.
        timestamp: Expiration / occurrence timestamp.
        retry_count: Attempt number when failure occurred.
    """

    step_id: int
    error_message: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    retry_count: int = 0


@dataclass(frozen=True)
class ReflectionAnalysis:
    """Objective evaluation analysis produced by IReflectionStrategy.

    Attributes:
        goal_completed: Boolean indicating whether overall goal is satisfied.
        confidence: Confidence score between 0.0 and 1.0.
        retryable: Boolean indicating whether failure can be retried.
        missing_information: List of missing inputs or observations.
        suggested_action: Optional natural language recommendation.
    """

    goal_completed: bool
    confidence: float
    retryable: bool = True
    missing_information: list[str] = field(default_factory=list)
    suggested_action: str | None = None
