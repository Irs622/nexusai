"""Dynamic AI Tool Selector & Ranking Engine with Semantic Description Scoring."""
from typing import List, Dict, Any, Optional
from nexusai.tools.registry import ToolRegistry
from nexusai.tools.base import BaseTool

class ToolSelector:
    """Evaluates task descriptions and dynamically ranks tools using semantic description scoring."""

    def __init__(self, registry: ToolRegistry) -> None:
        self.registry = registry

    def score_tool(self, task_description: str, tool: BaseTool) -> float:
        """Calculate relevance score between task description and tool schema/description."""
        task_words = set(task_description.lower().split())
        tool_desc_words = set(tool.description.lower().split())
        tool_name_words = set(tool.name.lower().split("_"))

        # Jaccard / Overlap similarity score
        overlap_desc = len(task_words.intersection(tool_desc_words))
        overlap_name = len(task_words.intersection(tool_name_words))

        return (overlap_name * 2.0) + (overlap_desc * 1.0)

    def select_best_tool(self, task_description: str) -> BaseTool:
        """Select highest-ranked tool for a given task description."""
        tools = self.registry.get_all_tools()
        if not tools:
            raise ValueError("No tools registered in ToolRegistry.")

        best_tool: Optional[BaseTool] = None
        best_score: float = -1.0

        for tool in tools:
            score = self.score_tool(task_description, tool)
            if score > best_score:
                best_score = score
                best_tool = tool

        return best_tool or tools[0]
