"""
Long-Term Memory Tools for storing and recalling semantic facts.
"""

from __future__ import annotations
from typing import Any
from pydantic import BaseModel, Field

from nexusai.knowledge.vector import VectorKnowledgeBase
from nexusai.security.guard import RiskLevel
from nexusai.tools.base import BaseTool


class RememberFactInputSchema(BaseModel):
    """Input schema for knowledge_remember_fact tool."""

    fact: str = Field(..., description="The fact, preference, or solution string to remember long-term")


class RememberFactTool(BaseTool):
    """Tool for storing semantic facts into ChromaDB long-term memory."""

    name = "knowledge_remember_fact"
    description = (
        "Stores an important fact, user preference, or project detail into long-term memory. "
        "Use this when the user explicitly asks you to remember something, or when you solve a complex problem you should recall later."
    )
    risk_level = RiskLevel.LOW
    input_schema = RememberFactInputSchema

    def __init__(self, vector_kb: VectorKnowledgeBase | None = None) -> None:
        self.vector_kb = vector_kb or VectorKnowledgeBase()

    async def execute(self, fact: str, **kwargs: Any) -> str:
        """Store fact into vector database."""
        await self.vector_kb.store_memory(fact)
        return f"Fact successfully stored in long-term memory: '{fact}'"


class RecallFactInputSchema(BaseModel):
    """Input schema for knowledge_recall_fact tool."""

    query: str = Field(..., description="Semantic search query to retrieve past facts from long-term memory")


class RecallFactTool(BaseTool):
    """Tool for recalling relevant semantic facts from ChromaDB long-term memory."""

    name = "knowledge_recall_fact"
    description = "Searches long-term memory for past facts, preferences, or solutions using semantic search."
    risk_level = RiskLevel.LOW
    input_schema = RecallFactInputSchema

    def __init__(self, vector_kb: VectorKnowledgeBase | None = None) -> None:
        self.vector_kb = vector_kb or VectorKnowledgeBase()

    async def execute(self, query: str, **kwargs: Any) -> str:
        """Search vector database for relevant memories."""
        results = await self.vector_kb.search_memory(query)
        if not results:
            return "No relevant memories found."

        formatted_memories = "\n".join(f"- {memory}" for memory in results)
        return f"Retrieved long-term memories:\n{formatted_memories}"
