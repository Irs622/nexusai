"""Memory Hierarchy Coordinator with Context Compaction & Summarization."""
from typing import Any, Dict, List, Optional
from nexusai.memory.sqlite_memory import SQLiteMemory
from nexusai.knowledge.vector import VectorKnowledgeBase

class MemoryHierarchy:
    """Manages short-term working memory, session history, and long-term vector store."""

    def __init__(self, sqlite_memory: SQLiteMemory, vector_store: Optional[VectorKnowledgeBase] = None) -> None:
        self.sqlite_memory = sqlite_memory
        self.vector_store = vector_store

    async def initialize(self) -> None:
        """Initialize underlying databases."""
        await self.sqlite_memory.initialize_db()
        if self.vector_store is not None:
            await self.vector_store.initialize()

    async def record_interaction(self, session_id: str, role: str, content: str) -> None:
        """Save message turn to session memory."""
        await self.sqlite_memory.add_message(session_id, role, content)

    async def compact_history(self, session_id: str, max_turns: int = 10) -> str:
        """Compact old conversation turns into a summary representation."""
        messages = await self.sqlite_memory.get_messages(session_id, limit=100)
        if len(messages) <= max_turns:
            return "No compaction required."
            
        old_turns = messages[:-max_turns]
        summary_text = f"Compacted Summary of {len(old_turns)} turns: " + " | ".join([m["content"] for m in old_turns[:3]])
        
        if self.vector_store is not None:
            await self.vector_store.store_memory(summary_text, metadata={"session_id": session_id, "type": "compacted_summary"})
            
        return summary_text

    async def query_relevant_context(self, session_id: str, query: str, history_limit: int = 5) -> Dict[str, Any]:
        """Retrieve recent session turns and relevant long-term vector context."""
        recent_turns = await self.sqlite_memory.get_messages(session_id, limit=history_limit)
        
        vector_facts: List[str] = []
        if self.vector_store is not None:
            vector_facts = await self.vector_store.search_memory(query, n_results=3)

        return {
            "recent_turns": recent_turns,
            "vector_facts": vector_facts,
        }
