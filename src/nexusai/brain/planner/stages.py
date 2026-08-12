"""Modular Planner Pipeline stages and ScoringStrategy abstractions for NexusAI Agent Runtime."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable
from uuid import uuid4

from nexusai.brain.domain.agent import (
    ActionCandidate,
    CapabilityGraph,
    ConfidenceType,
    DecisionEvidence,
    DecisionOutcome,
    DecisionReasoning,
    DecisionTrace,
    ExecutionFailure,
    FailureReason,
    PlanGraph,
    PlanGraphNode,
    PlannerWeights,
    PlanningContext,
    PlanStep,
    RecoveryStrategy,
    RejectedCandidate,
    StepStatus,
)


@runtime_checkable
class IScoringStrategy(Protocol):
    """Protocol interface for candidate action scoring strategies."""

    def score(
        self,
        candidate_name: str,
        weights: PlannerWeights,
        success_prob: float = 0.9,
        info_gain: float = 0.8,
        latency_factor: float = 0.1,
        cost_factor: float = 0.05,
    ) -> ActionCandidate:
        """Calculate score and return ActionCandidate."""
        ...


class WeightedLinearStrategy:
    """Default linear scoring strategy using PlannerWeights."""

    def score(
        self,
        candidate_name: str,
        weights: PlannerWeights,
        success_prob: float = 0.9,
        info_gain: float = 0.8,
        latency_factor: float = 0.1,
        cost_factor: float = 0.05,
    ) -> ActionCandidate:
        w = weights
        score = (
            (w.success_weight * success_prob)
            + (w.info_weight * info_gain)
            - (w.latency_weight * latency_factor)
            - (w.cost_weight * cost_factor)
        )
        score = max(0.0, min(1.0, score))
        rejected = score < 0.3

        preconds: tuple[str, ...]
        if "file" in candidate_name:
            preconds = ("workspace_mounted", "path_resolved")
            effects = ("content_retrieved",)
        else:
            preconds = ("agent_ready",)
            effects = ("action_completed",)

        return ActionCandidate(
            name=candidate_name,
            score=round(score, 3),
            rationale=f"Weighted score: {score:.3f} (success={w.success_weight}, info={w.info_weight})",
            estimated_cost=cost_factor,
            estimated_reward=info_gain,
            preconditions=preconds,
            expected_effects=effects,
            rejected=rejected,
        )


class BayesianStrategy:
    """Bayesian scoring strategy estimating posterior probability of success."""

    def score(
        self,
        candidate_name: str,
        weights: PlannerWeights,
        success_prob: float = 0.9,
        info_gain: float = 0.8,
        latency_factor: float = 0.1,
        cost_factor: float = 0.05,
    ) -> ActionCandidate:
        prior = 0.5
        likelihood = success_prob
        score = (likelihood * prior) / ((likelihood * prior) + ((1 - likelihood) * (1 - prior)))
        score = round(score, 3)
        return ActionCandidate(
            name=candidate_name,
            score=score,
            rationale=f"Bayesian posterior score: {score:.3f}",
            estimated_cost=cost_factor,
            estimated_reward=info_gain,
            preconditions=("bayesian_prior_valid",),
            expected_effects=("posterior_calculated",),
            rejected=score < 0.3,
        )


class GoalAnalyzer:
    """Stage 1: Analyzes PlanningContext and extracts required capabilities and constraints."""

    def analyze(self, ctx: PlanningContext) -> dict[str, str]:
        return {
            "description": ctx.goal.description,
            "constraint_count": str(len(ctx.constraints)),
            "planning_mode": ctx.policy.mode.value,
        }


class TaskDecomposer:
    """Stage 2: Decomposes goal analysis into executable PlanStep items."""

    def decompose(self, ctx: PlanningContext, analysis: dict[str, str]) -> list[PlanStep]:
        steps: list[PlanStep] = []
        if ctx.available_tools:
            for idx, tool in enumerate(ctx.available_tools, 1):
                steps.append(
                    PlanStep(
                        step_id=idx,
                        title=f"Execute {tool}",
                        description=f"Invoke tool '{tool}' for goal: {ctx.goal.description}",
                        tool_name=tool,
                        status=StepStatus.PENDING,
                    )
                )
        else:
            steps.append(
                PlanStep(
                    step_id=1,
                    title="Direct Answer",
                    description=f"Formulate answer for goal: {ctx.goal.description}",
                    status=StepStatus.PENDING,
                )
            )
        return steps


class DependencyResolver:
    """Stage 3: Dynamically resolves semantic dependencies via CapabilityGraph and explicit step declarations."""

    def resolve(
        self,
        steps: list[PlanStep],
        graph: CapabilityGraph | None = None,
        auto_insert: bool = True,
    ) -> PlanGraph:
        cap_graph = graph or CapabilityGraph()
        final_steps: list[PlanStep] = []
        tool_to_step_id: dict[str, int] = {}
        seen_tools: set[str] = set()

        for step in steps:
            if auto_insert and step.tool_name and step.tool_name in cap_graph.requirements:
                reqs = cap_graph.requirements[step.tool_name]
                for req_tool in reqs:
                    if req_tool not in seen_tools:
                        req_step_id = len(final_steps) + 1
                        req_step = PlanStep(
                            step_id=req_step_id,
                            title=f"Auto-Prerequisite: {req_tool}",
                            description=f"Auto-inserted prerequisite '{req_tool}' required for '{step.tool_name}'",
                            tool_name=req_tool,
                            status=StepStatus.PENDING,
                        )
                        final_steps.append(req_step)
                        seen_tools.add(req_tool)
                        tool_to_step_id[req_tool] = req_step_id

            if step.step_id is None or step.step_id <= 0:
                step.step_id = len(final_steps) + 1

            final_steps.append(step)
            if step.tool_name:
                seen_tools.add(step.tool_name)
                tool_to_step_id[step.tool_name] = step.step_id

        nodes: dict[Any, PlanGraphNode] = {}
        edges: list[tuple[Any, Any]] = []

        for st in final_steps:
            node_deps: list[Any] = []

            # 1. Add explicit step dependencies declared on step.depends_on
            if hasattr(st, "depends_on") and st.depends_on:
                for dep in st.depends_on:
                    node_deps.append(dep)

            # 2. Add capability graph tool prerequisites if present
            if st.tool_name and st.tool_name in cap_graph.requirements:
                for req_tool in cap_graph.requirements[st.tool_name]:
                    if req_tool in tool_to_step_id:
                        parent_id = tool_to_step_id[req_tool]
                        if parent_id != st.step_id and parent_id not in node_deps:
                            node_deps.append(parent_id)

            # Preserve explicit dependencies tuple (deduplicated & sorted for determinism)
            unique_deps = tuple(sorted(set(node_deps), key=lambda d: (type(d).__name__, str(d))))
            nodes[st.step_id] = PlanGraphNode(step=st, dependencies=unique_deps)

            for dep in unique_deps:
                edges.append((dep, st.step_id))

        return PlanGraph(nodes=nodes, edges=tuple(edges))


class ActionRanker:
    """Stage 4: Ranks candidate actions using pluggable IScoringStrategy."""

    def __init__(self, strategy: IScoringStrategy | None = None) -> None:
        self.strategy = strategy or WeightedLinearStrategy()

    def score_candidate(self, candidate_name: str, weights: PlannerWeights) -> ActionCandidate:
        return self.strategy.score(candidate_name, weights)

    def rank(
        self, candidates: list[ActionCandidate]
    ) -> tuple[list[ActionCandidate], list[RejectedCandidate]]:
        ranked = sorted(candidates, key=lambda c: c.score, reverse=True)
        rejected: list[RejectedCandidate] = []
        for c in candidates:
            if c.rejected:
                rejected.append(
                    RejectedCandidate(
                        name=c.name,
                        score=c.score,
                        rejection_reason="Utility score below 0.3 threshold",
                    )
                )

        return ranked, rejected


class RecoveryPlanner:
    """Domain Failure Model: Evaluates ExecutionFailure and produces RecoveryStrategy and recovery steps."""

    def plan_recovery(self, failure: ExecutionFailure) -> tuple[RecoveryStrategy, PlanStep | None]:
        if failure.reason == FailureReason.TIMEOUT:
            return RecoveryStrategy.RETRY, PlanStep(
                step_id=99,
                title=f"Retry {failure.tool_name}",
                description=f"Retry failed tool '{failure.tool_name}' with extended timeout",
                tool_name=failure.tool_name,
                status=StepStatus.PENDING,
            )
        elif failure.reason == FailureReason.MISSING_DEPENDENCY:
            return RecoveryStrategy.REPLAN, None
        else:
            return RecoveryStrategy.FAIL, None


class ExecutionPlanner:
    """Stage 5 Pure Orchestrator: Drives pipeline stages sequentially without embedded domain heuristics."""

    def __init__(
        self,
        analyzer: GoalAnalyzer | None = None,
        decomposer: TaskDecomposer | None = None,
        resolver: DependencyResolver | None = None,
        ranker: ActionRanker | None = None,
    ) -> None:
        self.analyzer = analyzer or GoalAnalyzer()
        self.decomposer = decomposer or TaskDecomposer()
        self.resolver = resolver or DependencyResolver()
        self.ranker = ranker or ActionRanker()

    def plan(
        self, ctx: PlanningContext, session_id: str = "session-1"
    ) -> tuple[PlanGraph, DecisionTrace]:
        analysis = self.analyzer.analyze(ctx)
        raw_steps = self.decomposer.decompose(ctx, analysis)
        plan_graph = self.resolver.resolve(
            raw_steps,
            graph=ctx.resources_component.capability_graph,
            auto_insert=ctx.policy.auto_insert_missing_dependencies,
        )

        candidate_objs: list[ActionCandidate] = []
        for tool in ctx.available_tools or ("default_action",):
            cand = self.ranker.score_candidate(tool, weights=ctx.policy.weights)
            candidate_objs.append(cand)

        ranked, rejected = self.ranker.rank(candidate_objs)
        selected_name = ranked[0].name if ranked else "default_action"
        top_score = ranked[0].score if ranked else 1.0

        trace = DecisionTrace(
            trace_id=str(uuid4()),
            session_id=session_id,
            turn_index=1,
            goal_description=ctx.goal.description,
            evidence=DecisionEvidence(
                reasoning_steps=(
                    f"Analyzed goal '{ctx.goal.description}'",
                    f"Evaluated {len(candidate_objs)} candidates via CapabilityGraph",
                    f"Selected '{selected_name}' with score {top_score:.3f}",
                )
            ),
            outcome=DecisionOutcome(
                chosen_action=selected_name,
                confidence=top_score,
                confidence_type=ConfidenceType.PLANNER,
            ),
            candidate_rankings=tuple(ranked),
            rejected_candidates=tuple(rejected),
            policy_used=ctx.policy,
            reasoning=DecisionReasoning(
                candidate_actions=tuple(c.name for c in ranked),
                selected_action=selected_name,
                reason=f"Selected '{selected_name}' (score {top_score:.3f}) via CapabilityGraph",
                confidence=top_score,
            ),
        )

        return plan_graph, trace
