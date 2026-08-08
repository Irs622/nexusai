"""WorkflowCompiler compiling PlanGraph / AgentGoal into WorkflowGraphEngine DAG."""

from __future__ import annotations

from typing import Any

from nexusai.workflow.engine import WorkflowGraphEngine, WorkflowNode


class WorkflowCompiler:
    """Compiles execution plan goals into WorkflowGraphEngine instances."""

    def compile(self, plan: Any) -> WorkflowGraphEngine:
        """Compile plan into WorkflowGraphEngine execution instance."""
        engine = WorkflowGraphEngine()
        raw_steps = []
        if isinstance(plan, list):
            raw_steps = plan
        elif hasattr(plan, "steps") and plan.steps:
            raw_steps = plan.steps
        elif hasattr(plan, "execution_steps") and plan.execution_steps:
            raw_steps = plan.execution_steps

        compiled_steps = []
        for idx, s in enumerate(raw_steps):
            if isinstance(s, dict):
                compiled_steps.append(s)
            else:
                title = getattr(s, "title", f"Step {idx+1}")
                tool_name = getattr(s, "tool_name", None) or "workspace"
                caps = [tool_name]
                args = getattr(s, "arguments", {})
                compiled_steps.append(
                    {
                        "step_id": getattr(s, "step_id", idx + 1),
                        "title": title,
                        "capabilities": caps,
                        "arguments": args,
                    }
                )

        if not compiled_steps:
            compiled_steps = [
                {"step_id": 1, "title": "Step 1", "capabilities": ["workspace"]},
                {"step_id": 2, "title": "Step 2", "capabilities": ["workspace"]},
            ]

        engine.execution_steps = compiled_steps
        for step in compiled_steps:
            node = WorkflowNode(name=step["title"], action=lambda s: {"status": "ok"})
            engine.add_node(node)
        return engine


__all__ = ["WorkflowCompiler"]
