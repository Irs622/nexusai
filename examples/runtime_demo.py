"""Runtime & Observability Demo — ExecutionEngine, Policy, CircuitBreaker, Spans & Learning Loop."""

from __future__ import annotations

import asyncio

from nexusai.brain.domain.agent import (
    AgentGoal,
    PlanningConstraints,
    PlanningContext,
    PlanningGoal,
    PlanningResources,
)
from nexusai.brain.eval.decision_dataset import DecisionDataset
from nexusai.brain.eval.learning import OfflineEvaluator
from nexusai.brain.planner.engine import PlanGraphExecutionEngine
from nexusai.brain.ports.tool_port import IToolPort, ToolExecutionRequest, ToolExecutionResult
from nexusai.brain.runtime.execution_policy import ExecutionPolicy
from nexusai.brain.runtime.resource_manager import ResourceBudget, ResourceManager
from nexusai.brain.telemetry.spans import ExecutionSpan, TraceCollector


class RuntimeToolPort(IToolPort):
    async def execute(self, request: ToolExecutionRequest) -> ToolExecutionResult:
        await asyncio.sleep(0.05)  # Simulate I/O execution latency
        return ToolExecutionResult(
            request_id=request.execution_id,
            tool_name=request.tool_name,
            success=True,
            result_data=f"Output data for {request.tool_name}",
        )


async def main() -> None:
    print("=== NexusAI Agent Runtime Engine Demo ===")

    # 1. Setup Resource Budget and Observability Trace Collector
    _resource_manager = ResourceManager(
        budget=ResourceBudget(max_concurrent_workers=4, token_budget_units=32000)
    )
    trace_collector = TraceCollector()

    span_planner = ExecutionSpan(name="planner.plan", duration_ms=12.5)
    trace_collector.record_span(span_planner)

    # 2. Configure PlanningContext
    goal = AgentGoal(description="Locate file, read contents, and produce executive summary")
    ctx = PlanningContext(
        goal_component=PlanningGoal(goal=goal),
        resources_component=PlanningResources(available_tools=("summarize_file",)),
        constraints_component=PlanningConstraints(time_budget_sec=60.0, token_budget_units=32000),
    )

    # 3. Instantiate Engine & Execute
    engine = PlanGraphExecutionEngine(
        policy=ExecutionPolicy(timeout_sec=30.0, enable_circuit_breaker=True)
    )
    tool_port = RuntimeToolPort()

    print(f"Goal: {goal.description}")
    print("Executing PlanGraph through PlanGraphExecutionEngine...")

    graph, results, trace = await engine.execute_plan(
        ctx, tool_port=tool_port, session_id="sess-runtime-demo"
    )

    span_tool = ExecutionSpan(name="tool.execute", duration_ms=52.0)
    trace_collector.record_span(span_tool)

    print(f"\nExecution Finished! Total Steps Executed: {len(results)}")

    # 4. Record Decision in DecisionDataset and evaluate strategy
    dataset = DecisionDataset()
    dataset.record_decision(trace, outcome_success=True, execution_latency_ms=64.5, reward=1.0)

    evaluator = OfflineEvaluator()
    summary = evaluator.evaluate_dataset(dataset)

    print("\nOffline Strategy Learning Loop Metrics:")
    print(f"  - Total Decisions : {summary.total_decisions}")
    print(f"  - Win Rate        : {summary.win_rate * 100:.1f}%")
    print(f"  - Mean Latency    : {summary.mean_latency_ms:.2f} ms")
    print(f"  - Mean Reward     : {summary.mean_reward:.2f}")

    print("\nTelemetry Spans Latency Breakdown:")
    for span_name, latency in trace_collector.get_latency_breakdown().items():
        print(f"  - {span_name}: {latency:.1f} ms")


if __name__ == "__main__":
    asyncio.run(main())
