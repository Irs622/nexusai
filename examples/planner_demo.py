"""Planner Pipeline Demo — NexusAI Modular ExecutionPlanner & PlanValidator."""

from __future__ import annotations

from nexusai.brain.domain.agent import (
    AgentGoal,
    PlanningConstraints,
    PlanningContext,
    PlanningGoal,
    PlanningResources,
)
from nexusai.brain.planner.stages import ExecutionPlanner
from nexusai.brain.planner.validator import PlanValidator


def main() -> None:
    print("=== NexusAI Modular Planner Demo ===")

    goal = AgentGoal(description="Analyze codebase metrics and summarize target document")
    ctx = PlanningContext(
        goal_component=PlanningGoal(goal=goal),
        resources_component=PlanningResources(available_tools=("summarize_file",)),
        constraints_component=PlanningConstraints(time_budget_sec=30.0, token_budget_units=16000),
    )

    planner = ExecutionPlanner()
    plan_graph, trace = planner.plan(ctx, session_id="demo-planner-session")

    print(f"Goal: {goal.description}")
    print(
        f"Generated PlanGraph DAG with {len(plan_graph.nodes)} steps and {len(plan_graph.edges)} dependency edges:"
    )

    for node_id, node in plan_graph.nodes.items():
        deps = node.dependencies
        print(f"  Node {node_id}: {node.step.title} (Tool: {node.step.tool_name}) [Deps: {deps}]")

    print("\nValidating PlanGraph via PlanValidator...")
    validator = PlanValidator()
    val_result = validator.validate(plan_graph, constraints=ctx.constraints_component)

    print(f"Validation Is Valid: {val_result.is_valid}")
    for issue in val_result.issues:
        print(f"  - [{issue.severity.value}] {issue.code}: {issue.message}")


if __name__ == "__main__":
    main()
