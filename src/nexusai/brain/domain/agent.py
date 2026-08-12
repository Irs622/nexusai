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


class ConfidenceType(str, Enum):
    """Source classification for confidence scores."""

    PLANNER = "PLANNER"
    TOOL_SELECTION = "TOOL_SELECTION"
    MEMORY_MATCH = "MEMORY_MATCH"
    LLM_SELF_ESTIMATE = "LLM_SELF_ESTIMATE"


class PlanningMode(str, Enum):
    """Execution planning mode classification."""

    FAST = "FAST"
    BALANCED = "BALANCED"
    CHEAP = "CHEAP"
    HIGH_ACCURACY = "HIGH_ACCURACY"


class FailureReason(str, Enum):
    """Domain execution failure classification."""

    TOOL_EXECUTION_ERROR = "TOOL_EXECUTION_ERROR"
    TIMEOUT = "TIMEOUT"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    MISSING_DEPENDENCY = "MISSING_DEPENDENCY"
    RESOURCE_EXHAUSTED = "RESOURCE_EXHAUSTED"


class RecoveryStrategy(str, Enum):
    """Recovery strategy classification for plan recovery."""

    RETRY = "RETRY"
    FALLBACK_TOOL = "FALLBACK_TOOL"
    REPLAN = "REPLAN"
    SKIP = "SKIP"
    FAIL = "FAIL"


class ValidationSeverity(str, Enum):
    """Validation issue severity level."""

    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


@dataclass(frozen=True)
class ValidationIssue:
    """Individual plan graph validation issue."""

    severity: ValidationSeverity
    code: str
    message: str
    step_id: int | str | None = None


@dataclass(frozen=True)
class ValidationResult:
    """Plan validation result report."""

    is_valid: bool
    issues: tuple[ValidationIssue, ...] = ()


@dataclass(frozen=True)
class CapabilityGraph:
    """Graph mapping tool capability dependencies (e.g. summarize_file -> read_file -> locate_file)."""

    requirements: dict[str, tuple[str, ...]] = field(
        default_factory=lambda: dict[str, tuple[str, ...]](
            {
                "summarize_file": ("read_file",),
                "read_file": ("locate_file",),
            }
        )
    )


@dataclass(frozen=True)
class PlannerWeights:
    """Configurable scoring weights for candidate action utility scoring."""

    success_weight: float = 0.45
    info_weight: float = 0.30
    latency_weight: float = 0.15
    cost_weight: float = 0.10


@dataclass(frozen=True)
class PlanningPolicy:
    """Configurable planning policy passed within PlanningContext."""

    mode: PlanningMode = PlanningMode.BALANCED
    weights: PlannerWeights = field(default_factory=PlannerWeights)
    auto_insert_missing_dependencies: bool = True


@dataclass(frozen=True)
class AgentGoal:
    """Canonical goal definition provided to Agent Runtime."""

    description: str
    goal_id: UUID = field(default_factory=uuid4)
    constraints: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class PlanningGoal:
    """Decomposed goal component of PlanningContext."""

    goal: AgentGoal
    constraints: tuple[str, ...] = ()


@dataclass(frozen=True)
class PlanningResources:
    """Decomposed resources component of PlanningContext."""

    available_tools: tuple[str, ...] = ()
    capability_graph: CapabilityGraph = field(default_factory=CapabilityGraph)
    memory_summary: str = ""
    conversation_summary: str = ""


@dataclass(frozen=True)
class PlanningConstraints:
    """Decomposed constraints component of PlanningContext."""

    time_budget_sec: float = 60.0
    token_budget_units: int = 32000


@dataclass
class PlanStep:
    """Individual executable step within an AgentPlan."""

    step_id: int | str
    title: str
    description: str = ""
    tool_name: str | None = None
    arguments: dict[str, Any] = field(default_factory=dict)
    status: StepStatus = StepStatus.PENDING
    depends_on: tuple[Any, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class PlanGraphNode:
    """DAG Graph Node wrapping a PlanStep with explicit dependency step IDs."""

    step: PlanStep
    dependencies: tuple[int | str, ...] = ()


@dataclass(frozen=True)
class PlanGraph:
    """DAG Execution Plan container storing nodes and dependency edges."""

    nodes: dict[int | str, PlanGraphNode] = field(default_factory=dict)
    edges: tuple[tuple[int | str, int | str], ...] = ()


@dataclass(frozen=True)
class FailureRecord:
    """Failure record documenting an execution error."""

    step_id: int | str
    error_message: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    retry_count: int = 0


@dataclass(frozen=True)
class ExecutionFailure:
    """Structured domain failure model for recovery planning."""

    step_id: int | str
    tool_name: str
    reason: FailureReason
    error_message: str
    timestamp: float = field(default_factory=lambda: datetime.now(timezone.utc).timestamp())


@dataclass(frozen=True)
class ReflectionAnalysis:
    """Objective evaluation analysis produced by IReflectionStrategy."""

    goal_completed: bool
    confidence: float
    retryable: bool = True
    missing_information: list[str] = field(default_factory=list)
    suggested_action: str | None = None


@dataclass(frozen=True)
class ScoringEvidenceFactor:
    """Explaining how an individual scoring factor contributed to candidate utility score."""

    factor_name: str
    raw_value: float
    weight: float
    weighted_score: float
    rationale: str


@dataclass(frozen=True)
class ActionCandidate:
    """Evaluated action candidate considered during decision selection."""

    name: str
    score: float = 0.0
    rationale: str = ""
    estimated_cost: float = 0.0
    estimated_reward: float = 0.0
    preconditions: tuple[str, ...] = ()
    expected_effects: tuple[str, ...] = ()
    evidence_factors: tuple[ScoringEvidenceFactor, ...] = ()
    rejected: bool = False


@dataclass(frozen=True)
class RejectedCandidate:
    """Explicit record of candidate rejection during process of elimination."""

    name: str
    score: float
    rejection_reason: str


@dataclass(frozen=True)
class DecisionEvidence:
    """Decomposed decision evidence reasoning container."""

    reasoning_steps: tuple[str, ...] = ()
    constraint_analysis: tuple[str, ...] = ()
    cost_estimation: float = 0.0


@dataclass(frozen=True)
class DecisionOutcome:
    """Decomposed decision outcome container."""

    chosen_action: str = ""
    confidence: float = 1.0
    confidence_type: ConfidenceType = ConfidenceType.PLANNER


@dataclass(frozen=True)
class DecisionReasoning:
    """Explaining WHY an agent chose a specific action step."""

    candidate_actions: tuple[str, ...] = ()
    selected_action: str = ""
    reason: str = ""
    confidence: float = 1.0


@dataclass(frozen=True)
class DecisionTrace:
    """Immutable trace container recording WHY actions were selected across turn iterations (v3)."""

    trace_id: str
    session_id: str
    turn_index: int
    goal_description: str
    evidence: DecisionEvidence = field(default_factory=DecisionEvidence)
    outcome: DecisionOutcome = field(default_factory=DecisionOutcome)
    candidate_rankings: tuple[ActionCandidate, ...] = ()
    rejected_candidates: tuple[RejectedCandidate, ...] = ()
    policy_used: PlanningPolicy = field(default_factory=PlanningPolicy)
    reasoning: DecisionReasoning = field(default_factory=DecisionReasoning)
    timestamp: float = field(default_factory=lambda: datetime.now(timezone.utc).timestamp())


@dataclass(frozen=True)
class PlanningContext:
    """Decomposed, decoupled context payload provided to Planner Pipeline stages."""

    goal_component: PlanningGoal
    resources_component: PlanningResources = field(default_factory=PlanningResources)
    constraints_component: PlanningConstraints = field(default_factory=PlanningConstraints)
    policy: PlanningPolicy = field(default_factory=PlanningPolicy)

    @property
    def goal(self) -> AgentGoal:
        return self.goal_component.goal

    @property
    def available_tools(self) -> tuple[str, ...]:
        return self.resources_component.available_tools

    @property
    def constraints(self) -> tuple[str, ...]:
        return self.goal_component.constraints
