"""Reflection & Plan Repair Demo — Expectation-Gap Diagnostics and DAG Re-patching."""

from __future__ import annotations

from nexusai.brain.domain.agent import (
    ExecutionFailure,
    FailureReason,
    PlanGraph,
    PlanGraphNode,
    PlanStep,
    StepStatus,
)
from nexusai.brain.domain.world import WorldState
from nexusai.brain.planner.repair import PlanRepairEngine
from nexusai.brain.reflection.engine import ReflectionEngine


def main() -> None:
    print("=== NexusAI ReflectionEngine & PlanRepairEngine Demo ===")

    # 1. Create WorldState & ReflectionEngine
    world = WorldState(workspace_path="/project/workspace", connected_mcp_servers=("mcp-server-1",))
    reflection_engine = ReflectionEngine()
    repair_engine = PlanRepairEngine()

    # 2. Define failing plan step and ExecutionFailure
    failing_step = PlanStep(
        step_id=1,
        title="Read Target Document",
        description="Attempting to read document via remote OCR tool",
        tool_name="cloud_ocr_read",
        status=StepStatus.FAILED,
    )

    nodes = {1: PlanGraphNode(step=failing_step, dependencies=())}
    original_graph = PlanGraph(nodes=nodes, edges=())

    failure = ExecutionFailure(
        step_id=1,
        tool_name="cloud_ocr_read",
        reason=FailureReason.TIMEOUT,
        error_message="Remote API connection timed out after 30.0s",
    )

    print(
        f"Failing Tool Execution: Step 1 ({failing_step.tool_name}) | Error: {failure.error_message}"
    )

    # 3. Analyze failure via ReflectionEngine
    reflection = reflection_engine.reflect_on_failure(failing_step, failure, world_state=world)

    print("\nReflection Diagnostic Analysis:")
    print(f"  - Expectation Gap : {reflection.expectation_gap}")
    print(f"  - Root Cause      : {reflection.root_cause}")
    print(f"  - Repair Directives: {reflection.repair_suggestion}")
    print(f"  - Confidence      : {reflection.confidence}")

    # 4. Mutate PlanGraph via PlanRepairEngine
    repaired_graph = repair_engine.repair_plan(original_graph, failure, reflection)

    print(f"\nRepaired PlanGraph DAG Nodes ({len(repaired_graph.nodes)} Total):")
    for nid, node in repaired_graph.nodes.items():
        print(f"  - Node {nid}: {node.step.title} (Tool: {node.step.tool_name})")


if __name__ == "__main__":
    main()
