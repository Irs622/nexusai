"""WorkflowCompiler translating GoalPlan to executable ExecutionPlan contract."""
import uuid
from typing import List, Dict, Any
from nexusai.domain.models import GoalPlan, ExecutionPlan

class WorkflowCompiler:
    """Compiles high-level GoalPlan into executable ExecutionPlan contract."""

    def compile(self, goal_plan: GoalPlan) -> ExecutionPlan:
        """Compile steps into ExecutionPlan contract."""
        steps_data: List[Dict[str, Any]] = []
        
        for step in goal_plan.steps:
            steps_data.append({
                "step_id": step.step_id,
                "title": step.title,
                "description": step.description,
                "capabilities": step.required_capabilities,
            })

        return ExecutionPlan(
            plan_id=str(uuid.uuid4()),
            goal_plan=goal_plan,
            execution_steps=steps_data,
        )
