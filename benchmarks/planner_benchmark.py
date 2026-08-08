"""Benchmark script measuring Planner Pipeline DAG generation throughput and latency."""

from __future__ import annotations

import time
from nexusai.brain.domain.agent import AgentGoal, PlanningConstraints, PlanningContext, PlanningGoal, PlanningResources
from nexusai.brain.planner.stages import ExecutionPlanner
from nexusai.brain.planner.validator import PlanValidator


def run_planner_benchmark(iterations: int = 100) -> dict[str, float]:
    """Execute benchmark over N planning iterations."""
    planner = ExecutionPlanner()
    validator = PlanValidator()

    goal = AgentGoal(description="Locate, read, and summarize system configuration file")
    ctx = PlanningContext(
        goal_component=PlanningGoal(goal=goal),
        resources_component=PlanningResources(available_tools=("summarize_file",)),
        constraints_component=PlanningConstraints(time_budget_sec=60.0, token_budget_units=32000),
    )

    t0 = time.perf_counter()
    for _ in range(iterations):
        plan_graph, trace = planner.plan(ctx, session_id="bench-session")
        validator.validate(plan_graph, constraints=ctx.constraints_component)

    total_time_sec = time.perf_counter() - t0
    avg_latency_ms = (total_time_sec / iterations) * 1000.0
    throughput_ops = iterations / total_time_sec

    print(f"=== Planner Pipeline Benchmark Results ({iterations} iterations) ===")
    print(f"  Total Duration   : {total_time_sec:.4f} s")
    print(f"  Avg Latency/Plan : {avg_latency_ms:.3f} ms")
    print(f"  Throughput       : {throughput_ops:.2f} plans/sec")

    return {
        "total_time_sec": total_time_sec,
        "avg_latency_ms": avg_latency_ms,
        "throughput_ops": throughput_ops,
    }


if __name__ == "__main__":
    run_planner_benchmark()
