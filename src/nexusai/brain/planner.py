"""Task Planner & Decomposition Engine for NexusAI."""
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

@dataclass
class TaskStep:
    """Individual executable step in a decomposed task plan."""
    step_id: int
    title: str
    description: str
    tool_name: Optional[str] = None
    arguments: Dict[str, Any] = field(default_factory=dict)
    completed: bool = False

@dataclass
class TaskPlan:
    """Complete decomposed plan generated from a high-level user prompt."""
    prompt: str
    steps: List[TaskStep] = field(default_factory=list)

class TaskPlanner:
    """Decomposes high-level natural language user goals into structured executable steps."""

    def plan(self, user_prompt: str) -> TaskPlan:
        """Parse user goal and return structured task plan."""
        prompt_lower = user_prompt.lower()
        steps: List[TaskStep] = []

        if "next" in prompt_lower or "todo" in prompt_lower or "app" in prompt_lower:
            steps = [
                TaskStep(1, "Create Directory Structure", "Initialize project root directory", "workspace_list_directory", {"path": "."}),
                TaskStep(2, "Generate Project Configuration", "Create pyproject.toml configuration file", "workspace_read_file", {"file_path": "pyproject.toml"}),
                TaskStep(3, "Execute Shell Setup", "Run initial environment checks", "execute_terminal", {"command": "echo 'Initializing NexusAI App'"}),
            ]
        else:
            steps = [
                TaskStep(1, "Analyze Workspace", "List files in workspace root", "workspace_list_directory", {"path": "."}),
                TaskStep(2, "Read Configuration", "Read pyproject.toml", "workspace_read_file", {"file_path": "pyproject.toml"}),
            ]

        return TaskPlan(prompt=user_prompt, steps=steps)
