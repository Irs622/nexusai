"""ScenarioRunner orchestrator running golden scenarios and returning EvaluationResult reports."""

from __future__ import annotations

import time
from uuid import uuid4

from nexusai.brain.builder import AgentRuntimeBuilder
from nexusai.brain.container import RuntimeDependencies
from nexusai.brain.domain.agent import AgentGoal
from nexusai.brain.domain.session import BrainSession
from nexusai.brain.eval.evaluator import AgentEvaluator, EvaluationResult
from nexusai.brain.eval.scenario import Scenario, ScenarioCorpus
from nexusai.brain.loop_executor import LoopExecutor
from nexusai.brain.ports.tool_port import IToolPort, ToolExecutionRequest, ToolExecutionResult
from nexusai.brain.runtime.state import SessionState
from nexusai.brain.telemetry.metrics import InMemoryMetricsCollector


class MockScenarioToolPort(IToolPort):
    """Deterministic Mock ToolPort generating realistic tool execution results for golden scenarios."""

    async def execute(self, request: ToolExecutionRequest) -> ToolExecutionResult:
        """Execute mock tool call for scenario."""
        tool_name = request.tool_name or "default_tool"
        return ToolExecutionResult(
            tool_name=tool_name,
            success=True,
            result=f"Mock result payload for tool '{tool_name}' arguments: {request.arguments}",
        )


class ScenarioRunner:
    """Orchestrates golden scenario dataset execution and returns structured EvaluationResult reports."""

    def __init__(
        self,
        deps: RuntimeDependencies | None = None,
        evaluator: AgentEvaluator | None = None,
    ) -> None:
        self.deps = deps or RuntimeDependencies()
        self.evaluator = evaluator or AgentEvaluator()

    async def run_scenario(self, scenario: Scenario) -> EvaluationResult:
        """Run a single golden scenario and evaluate results."""
        t0 = time.perf_counter()
        collector = InMemoryMetricsCollector()
        active_deps = RuntimeDependencies(
            planning_strategy=self.deps.planning_strategy,
            reflection_strategy=self.deps.reflection_strategy,
            decision_strategy=self.deps.decision_strategy,
            compaction_pipeline=self.deps.compaction_pipeline,
            failure_classifier=self.deps.failure_classifier,
            retention_policy=self.deps.retention_policy,
            context_budget=self.deps.context_budget,
            context_estimator=self.deps.context_estimator,
            metrics_collector=collector,
        )

        executor = LoopExecutor(deps=active_deps, tool_port=MockScenarioToolPort())

        facade = AgentRuntimeBuilder().build()
        facade._executor = executor

        session = BrainSession(session_id=uuid4(), conversation_id=uuid4())
        goal = AgentGoal(description=scenario.description)
        state = SessionState(provider_id="scenario-provider", active_model="scenario-v1")

        agent_ctx = facade.create_agent_context(session=session, goal=goal, state=state)

        final_memory = await executor.execute_loop(agent_ctx)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        return self.evaluator.evaluate(
            scenario_id=scenario.scenario_id,
            memory=final_memory,
            collector=collector,
            latency_ms=elapsed_ms,
        )

    async def run_corpus(self, corpus: ScenarioCorpus) -> list[EvaluationResult]:
        """Run full scenario corpus and return list of EvaluationResult reports."""
        results: list[EvaluationResult] = []
        for scenario in corpus.scenarios:
            res = await self.run_scenario(scenario)
            results.append(res)
        return results
