"""ContextBuilder runtime implementation providing non-destructive context compaction and token budgeting."""

from __future__ import annotations

from nexusai.brain.domain.memory import MemoryEntry, MemoryQuery
from nexusai.brain.ports.memory_port import IContextBuilder, IMemoryRetriever, IMemoryStore


def estimate_token_count(text: str) -> int:
    """Estimate token count for a text string using standard word factor ratio (1.3 tokens/word)."""
    words = text.split()
    return int(len(words) * 1.3) + 1


class ContextBuilder(IContextBuilder):
    """Non-destructive context builder enforcing token budget ceilings and priority selection."""

    def __init__(
        self,
        retriever: IMemoryRetriever,
        store: IMemoryStore,
        reserved_system_tokens: int = 500,
    ) -> None:
        self.retriever = retriever
        self.store = store
        self.reserved_system_tokens = reserved_system_tokens

    async def build_context(
        self,
        session_id: str,
        query_text: str,
        max_tokens: int = 4096,
    ) -> tuple[str, list[MemoryEntry]]:
        """Construct non-destructive context representation strictly respecting token budget limits."""
        query = MemoryQuery(
            session_id=session_id,
            query_text=query_text,
            top_k=10,
            min_relevance=0.1,  # Broader candidate pool for compaction selection
        )
        memories = await self.retriever.retrieve(query)

        available_token_budget = max(100, max_tokens - self.reserved_system_tokens)
        current_token_count = 0

        selected_memories: list[MemoryEntry] = []
        context_lines: list[str] = ["[RECALLED MEMORY CONTEXT]"]

        for entry in memories:
            entry_line = f"- [{entry.memory_type.value.upper()}] {entry.content}"
            entry_tokens = estimate_token_count(entry_line)

            if current_token_count + entry_tokens <= available_token_budget:
                context_lines.append(entry_line)
                selected_memories.append(entry)
                current_token_count += entry_tokens
            else:
                # Token budget ceiling reached: stop selecting lower-ranked entries
                break

        formatted_context = "\n".join(context_lines) if len(context_lines) > 1 else ""
        return formatted_context, selected_memories
