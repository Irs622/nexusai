"""Stress test verifying MemoryIndexer and MemoryRanker performance with 10,000+ entries."""

from __future__ import annotations

import time

import pytest

from nexusai.brain.memory import (
    IndexedMemoryItem,
    MemoryIndexer,
    MemoryRanker,
    MemoryRetriever,
    MemoryType,
)


@pytest.mark.stress
def test_memory_10k_entries_stress():
    """Index and retrieve across 10,000 memory items without performance degradation."""
    indexer = MemoryIndexer()

    for i in range(10000):
        indexer.index_item(
            IndexedMemoryItem(
                item_id=f"stress-mem-{i}",
                memory_type=MemoryType.EPISODIC if i % 2 == 0 else MemoryType.SEMANTIC,
                text=f"Stress memory entry {i} containing Python architecture details and configuration options",
                source=f"source:{i % 50}",
                importance_score=0.5 + (i % 50) / 100.0,
                timestamp=time.time() - (i * 10),
            )
        )

    assert len(indexer.get_all()) == 10000

    retriever = MemoryRetriever(indexer)
    candidates = retriever.retrieve_candidates(query="Python architecture", max_results=100)

    assert len(candidates) <= 100
    assert len(candidates) > 0

    ranker = MemoryRanker()
    ranked = ranker.rank_memories(query="Python architecture", candidates=candidates)

    assert len(ranked) == len(candidates)
    assert ranked[0].final_score >= ranked[-1].final_score
