"""Domain models, state machine taxonomy, observations, and plan fingerprinting for P3-4 Agent Loop."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
import time
from typing import Any, Mapping

from nexusai.brain.domain.agent import PlanGraph
from nexusai.brain.ports.tool_port import ToolExecutionResult


class AgentLoopState(str, Enum):
    """Lifecycle state machine for Planning -> Execution -> Observation Loop."""

    INITIALIZING = "INITIALIZING"
    PLANNING = "PLANNING"
    PLAN_VALIDATION = "PLAN_VALIDATION"
    READY_FOR_EXECUTION = "READY_FOR_EXECUTION"
    EXECUTING = "EXECUTING"
    OBSERVING = "OBSERVING"
    EVALUATING = "EVALUATING"
    REPLANNING = "REPLANNING"
    RECONCILING = "RECONCILING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


TERMINAL_LOOP_STATES = frozenset({
    AgentLoopState.COMPLETED,
    AgentLoopState.FAILED,
    AgentLoopState.CANCELLED,
})


@dataclass(frozen=True)
class AgentLoopConfig:
    """Immutable configuration parameters for AgentLoop control bounds."""

    max_iterations: int = 10
    max_replans: int = 5
    iteration_timeout_seconds: float = 300.0
    require_plan_validation: bool = True
    allow_replanning: bool = True

    def __post_init__(self) -> None:
        if self.max_iterations <= 0:
            raise ValueError("max_iterations must be greater than 0")
        if self.max_replans < 0:
            raise ValueError("max_replans cannot be negative")
        if self.iteration_timeout_seconds <= 0.0:
            raise ValueError("iteration_timeout_seconds must be greater than 0")


@dataclass(frozen=True)
class Observation:
    """Immutable domain representation of an execution cycle observation."""

    execution_id: str
    iteration: int
    node_results: tuple[ToolExecutionResult, ...]
    successful_nodes: int
    failed_nodes: int
    pending_nodes: int
    terminal: bool
    summary: str
    timestamp: float = field(default_factory=time.time)


@dataclass(frozen=True)
class LoopDecision:
    """Immutable decision output returned by IOutcomeEvaluator."""

    action: str  # "COMPLETED", "REPLAN", "RECONCILE", "FAILED"
    reason: str
    confidence: float = 1.0


@dataclass(frozen=True)
class AgentLoopResult:
    """Immutable final result output returned by IAgentLoop."""

    execution_id: str
    final_state: AgentLoopState
    iterations: int
    replans: int
    observations: tuple[Observation, ...]
    final_output: str
    duration_ms: float = 0.0


def compute_plan_fingerprint(plan_graph: PlanGraph) -> str:
    """Compute a SHA-256 canonical digest fingerprint of a PlanGraph for infinite loop detection."""
    nodes_summary: list[dict[str, Any]] = []
    for node_id in sorted(plan_graph.nodes.keys()):
        node = plan_graph.nodes[node_id]
        deps = tuple(sorted(node.dependencies))
        nodes_summary.append({
            "id": node_id,
            "tool": node.step.tool_name,
            "title": node.step.title,
            "deps": deps,
        })
    canonical_json = json.dumps(nodes_summary, sort_keys=True)
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
