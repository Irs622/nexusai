"""Memory Intelligence Demo — Indexing, Retrieval, Ranking, Conflict Resolution & Compression."""

from __future__ import annotations

import time

from nexusai.brain.memory import (
    ContextAssembler,
    IndexedMemoryItem,
    MemoryConflictResolver,
    MemoryIndexer,
    MemoryRanker,
    MemoryRetriever,
    MemoryType,
)


def main() -> None:
    print("=== NexusAI Memory Intelligence Engine Demo ===")

    indexer = MemoryIndexer()

    # 1. Add memory items with a conflict scenario
    item1 = IndexedMemoryItem(
        item_id="mem-1",
        memory_type=MemoryType.EPISODIC,
        text="User prefers VSCode editor for Python projects",
        source="user_pref:editor",
        importance_score=0.75,
        timestamp=time.time() - 3600.0,
    )
    item2 = IndexedMemoryItem(
        item_id="mem-2",
        memory_type=MemoryType.EPISODIC,
        text="User updated preferred editor to Antigravity IDE for all tasks",
        source="user_pref:editor",
        importance_score=0.95,
        timestamp=time.time() - 60.0,
    )
    item3 = IndexedMemoryItem(
        item_id="mem-3",
        memory_type=MemoryType.SEMANTIC,
        text="Project uses Python 3.12 target architecture with strict Mypy typing",
        source="config:python",
        importance_score=0.90,
    )

    indexer.index_item(item1)
    indexer.index_item(item2)
    indexer.index_item(item3)

    print(f"Indexed {len(indexer.get_all())} items across multi-tier memory store.")

    # 2. Retrieve candidates
    retriever = MemoryRetriever(indexer)
    candidates = retriever.retrieve_candidates(query="editor Python", max_results=5)
    print(f"Retrieved {len(candidates)} candidate memories for query 'editor Python'.")

    # 3. Rank memories with recency exponential decay
    ranker = MemoryRanker()
    ranked = ranker.rank_memories(query="editor Python", candidates=candidates)
    print("\nRanked Memory Breakdown:")
    for r in ranked:
        print(
            f"  - [{r.item.item_id}] Score={r.final_score} (Rel={r.relevance_score}, Rec={r.recency_score}, Conf={r.confidence_score}) | {r.item.text}"
        )

    # 4. Resolve conflicts
    resolver = MemoryConflictResolver()
    resolved = resolver.resolve_conflicts(ranked)
    print(f"\nResolved Conflicts: Retained {len(resolved)} non-contradictory memory items.")

    # 5. Assemble final compressed memory context summary
    assembler = ContextAssembler(indexer=indexer)
    context_summary = assembler.assemble_memory_context(query="editor Python")

    print("\nFinal Assembled Context Summary Payload:")
    print(context_summary)


if __name__ == "__main__":
    main()
