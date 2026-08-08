"""Abstract Base Class for NexusAI Tools."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel

from nexusai.core.annotations import stable
from nexusai.security.guard import RiskLevel


@stable
class BaseTool(ABC):
    """Abstract Base Class enforced for all NexusAI capabilities."""

    name: str
    description: str
    risk_level: RiskLevel
    input_schema: type[BaseModel]

    @abstractmethod
    async def execute(self, *args: Any, **kwargs: Any) -> Any:
        """Execute the tool capability asynchronously."""
        ...

    def to_json_schema(self) -> dict[str, Any]:
        """Export tool definition to LLM function calling schema format."""
        schema = self.input_schema.model_json_schema()
        schema.pop("title", None)
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": schema,
            },
        }
