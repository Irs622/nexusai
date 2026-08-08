"""Benchmark script measuring Memory Intelligence pipeline indexing, ranking, and retrieval latency."""

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


def run_memory_benchmark(items_count: int = 1000) -> dict[str, float]:
    """Execute benchmark indexing items_count memory items and performing pipeline retrieval."""
    indexer = MemoryIndexer()

    # 1. Indexing Benchmark
    t0 = time.perf_counter()
    for i in range(items_count):
        indexer.index_item(
            IndexedMemoryItem(
                item_id=f"mem-{i}",
                memory_type=MemoryType.EPISODIC if i % 2 == 0 else MemoryType.SEMANTIC,
                text=f"Memory statement {i} regarding Python architecture and VSCode editor settings",
                source=f"source:{i % 10}",
                importance_score=0.5 + (i % 50) / 100.0,
            )
        )
    indexing_time_ms = (time.perf_counter() - t0) * 1000.0

    # 2. Retrieval & Ranking Benchmark
    retriever = MemoryRetriever(indexer)
    ranker = MemoryRanker()
    resolver = MemoryConflictResolver()
    assembler = ContextAssembler(indexer=indexer)

    t1 = time.perf_counter()
    candidates = retriever.retrieve_candidates(query="Python editor", max_results=50)
    ranked = ranker.rank_memories(query="Python editor", candidates=candidates)
    resolved = resolver.resolve_conflicts(ranked)
    summary = assembler.assemble_memory_context(query="Python editor")
    retrieval_time_ms = (time.perf_counter() - t1) * 1000.0

    print(f"=== Memory Intelligence Benchmark Results ({items_count} items) ===")
    print(f"  Indexing Latency  : {indexing_time_ms:.3f} ms")
    print(f"  Retrieval Latency : {retrieval_time_ms:.3f} ms")
    print(f"  Retained Candidates: {len(resolved)}")

    return {
        "indexing_time_ms": indexing_time_ms,
        "retrieval_time_ms": retrieval_time_ms,
    }


if __name__ == "__main__":
    run_memory_benchmark()
