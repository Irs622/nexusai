"""
Unit tests for VectorKnowledgeBase, RememberFactTool, and RecallFactTool.
"""

import pytest
import chromadb

from nexusai.knowledge.vector import VectorKnowledgeBase
from nexusai.security.guard import RiskLevel
from nexusai.tools.knowledge.memory_tools import RecallFactTool, RememberFactTool
from nexusai.tools.registry import ToolRegistry


import uuid

@pytest.fixture
def ephemeral_kb() -> VectorKnowledgeBase:
    client = chromadb.EphemeralClient()
    col_name = f"test_col_{uuid.uuid4().hex}"
    return VectorKnowledgeBase(client=client, collection_name=col_name)


@pytest.mark.asyncio
async def test_vector_kb_store_and_search(ephemeral_kb: VectorKnowledgeBase) -> None:
    # Empty search
    empty_res = await ephemeral_kb.search_memory("Python")
    assert empty_res == []

    # Store memory
    doc_id = await ephemeral_kb.store_memory("User prefers dark mode UI for all apps")
    assert doc_id is not None

    # Search memory
    results = await ephemeral_kb.search_memory("dark mode", n_results=1)
    assert len(results) == 1
    assert "dark mode" in results[0]


@pytest.mark.asyncio
async def test_remember_and_recall_fact_tools(ephemeral_kb: VectorKnowledgeBase) -> None:
    remember_tool = RememberFactTool(vector_kb=ephemeral_kb)
    recall_tool = RecallFactTool(vector_kb=ephemeral_kb)

    assert remember_tool.name == "knowledge_remember_fact"
    assert remember_tool.risk_level == RiskLevel.LOW
    assert recall_tool.name == "knowledge_recall_fact"
    assert recall_tool.risk_level == RiskLevel.LOW

    # Recall before remembering
    empty_output = await recall_tool.execute(query="favorite database")
    assert empty_output == "No relevant memories found."

    # Store fact
    store_msg = await remember_tool.execute(fact="Favorite database is SQLite and ChromaDB")
    assert "Fact successfully stored" in store_msg

    # Recall fact
    recall_output = await recall_tool.execute(query="which database is preferred?")
    assert "Retrieved long-term memories:" in recall_output
    assert "SQLite and ChromaDB" in recall_output


def test_knowledge_tools_registry(ephemeral_kb: VectorKnowledgeBase) -> None:
    registry = ToolRegistry()
    registry.register(RememberFactTool(vector_kb=ephemeral_kb))
    registry.register(RecallFactTool(vector_kb=ephemeral_kb))

    assert registry.has_tool("knowledge_remember_fact")
    assert registry.has_tool("knowledge_recall_fact")

    schemas = registry.get_all_schemas()
    names = [s["function"]["name"] for s in schemas]
    assert "knowledge_remember_fact" in names
    assert "knowledge_recall_fact" in names
