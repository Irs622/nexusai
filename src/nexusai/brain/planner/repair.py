"""PlanRepairEngine for dynamically patching and mutating PlanGraph DAGs upon execution failure."""

from __future__ import annotations

from nexusai.brain.domain.agent import (
    ExecutionFailure,
    PlanGraph,
    PlanGraphNode,
    PlanStep,
    StepStatus,
)
from nexusai.brain.reflection.engine import ReflectionResult


class PlanRepairEngine:
    """Dynamically mutates and patches PlanGraph DAG nodes upon failure based on ReflectionResult."""

    def repair_plan(
        self,
        graph: PlanGraph,
        failure: ExecutionFailure,
        reflection: ReflectionResult,
    ) -> PlanGraph:
        """Mutate PlanGraph by replacing or inserting fallback step nodes."""
        failed_node_id = failure.step_id
        if failed_node_id not in graph.nodes:
            return graph

        new_nodes = dict(graph.nodes)
        failed_node = new_nodes[failed_node_id]

        # Construct fallback replacement step
        fallback_step_id = max(graph.nodes.keys()) + 1
        fallback_step = PlanStep(
            step_id=fallback_step_id,
            title=f"Fallback for Step {failed_node_id}",
            description=f"Auto-inserted fallback step based on repair suggestion: {reflection.repair_suggestion}",
            tool_name="locate_file",  # Fallback to safe locator
            arguments={"query": failure.tool_name},
            status=StepStatus.PENDING,
        )

        fallback_node = PlanGraphNode(step=fallback_step, dependencies=failed_node.dependencies)
        new_nodes[fallback_step_id] = fallback_node

        # Update dependencies of child nodes pointing to failed_node_id
        new_edges: list[tuple[int, int]] = []
        for parent, child in graph.edges:
            if parent == failed_node_id:
                new_edges.append((fallback_step_id, child))
            else:
                new_edges.append((parent, child))

        return PlanGraph(nodes=new_nodes, edges=tuple(new_edges))
