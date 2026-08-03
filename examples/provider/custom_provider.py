"""Example custom model provider adapter for NexusAI."""
from typing import Any, Dict, List, Optional
from nexusai.models.base import BaseModelProvider

class MockModelProvider(BaseModelProvider):
    async def generate_response(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        system_prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        return {
            "type": "text",
            "content": "This is a mock LLM response."
        }
