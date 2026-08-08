"""ContextAssembler orchestrating the complete Memory Intelligence pipeline."""

from __future__ import annotations

from nexusai.brain.memory.compressor import ContextCompressor
from nexusai.brain.memory.conflict_resolver import MemoryConflictResolver
from nexusai.brain.memory.indexer import MemoryIndexer
from nexusai.brain.memory.policy import MemoryPolicy
from nexusai.brain.memory.ranker import MemoryRanker
from nexusai.brain.memory.retriever import MemoryRetriever


class ContextAssembler:
    """Orchestrates MemoryIndexer -> Retriever -> Ranker -> ConflictResolver -> Compressor."""

    def __init__(
        self,
        indexer: MemoryIndexer | None = None,
        retriever: MemoryRetriever | None = None,
        ranker: MemoryRanker | None = None,
        conflict_resolver: MemoryConflictResolver | None = None,
        compressor: ContextCompressor | None = None,
        policy: MemoryPolicy | None = None,
    ) -> None:
        self.indexer = indexer or MemoryIndexer()
        self.retriever = retriever or MemoryRetriever(self.indexer)
        self.ranker = ranker or MemoryRanker()
        self.conflict_resolver = conflict_resolver or MemoryConflictResolver()
        self.compressor = compressor or ContextCompressor()
        self.policy = policy or MemoryPolicy()

    def assemble_memory_context(self, query: str) -> str:
        """Execute complete memory pipeline and return optimal memory summary text."""
        candidates = self.retriever.retrieve_candidates(
            query=query, max_results=self.policy.max_retained_items
        )
        ranked = self.ranker.rank_memories(query=query, candidates=candidates)
        resolved = self.conflict_resolver.resolve_conflicts(ranked)
        _, summary_text = self.compressor.compress_memories(
            resolved, max_units=self.policy.max_context_units
        )
        return summary_text
