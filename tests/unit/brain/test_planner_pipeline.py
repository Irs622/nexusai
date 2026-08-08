"""Unit tests for Phase 6 TraceCollector, ResourceManager, AdaptiveBudgetStrategy, and DeduplicatingClusterCompressor."""

from __future__ import annotations

from nexusai.brain.domain.agent import PlannerWeights
from nexusai.brain.eval.decision_dataset import DecisionDataset, DecisionTrace
from nexusai.brain.eval.learning import OfflineEvaluator, StrategyTrainer
from nexusai.brain.memory import (
    DeduplicatingClusterCompressor,
    IndexedMemoryItem,
    MemoryType,
    RankedMemoryItem,
)
from nexusai.brain.runtime.resource_manager import (
    ResourceBudget,
    ResourceManager,
)
from nexusai.brain.telemetry.spans import ExecutionSpan, TraceCollector


def test_trace_collector_and_spans():
    """Verify TraceCollector records spans and calculates latency breakdowns."""
    collector = TraceCollector()

    span1 = ExecutionSpan(name="planner.plan", duration_ms=15.0)
    span2 = ExecutionSpan(name="tool.execute", duration_ms=45.0)

    collector.record_span(span1)
    collector.record_span(span2)

    breakdown = collector.get_latency_breakdown()

    assert breakdown["planner.plan"] == 15.0
    assert breakdown["tool.execute"] == 45.0


def test_resource_manager_quota_and_adaptive_adaptation():
    """Verify ResourceManager enforces concurrency/token budgets and computes adaptive budget scaling."""
    rm = ResourceManager(budget=ResourceBudget(max_concurrent_workers=4, token_budget_units=100))

    rm.acquire_worker()

    # Low resource consumption -> standard concurrency & full context units
    adaptation = rm.compute_adaptive_adaptation()
    assert adaptation.target_concurrency == 4
    assert adaptation.recommend_cheap_model is False

    # Consume 90% of token budget -> triggers cheap model & concurrency reduction
    rm.consume_tokens_and_cost(tokens=90, cost_usd=0.1)
    adaptation_heavy = rm.compute_adaptive_adaptation()
    assert adaptation_heavy.target_concurrency == 1
    assert adaptation_heavy.recommend_cheap_model is True


def test_learning_loop_strategy_trainer():
    """Verify OfflineEvaluator computes metrics and StrategyTrainer tunes PlannerWeights."""
    dataset = DecisionDataset()
    evaluator = OfflineEvaluator()
    trainer = StrategyTrainer()

    # Create dummy trace & dataset entry
    trace = DecisionTrace(
        trace_id="t-1", session_id="s-1", turn_index=0, goal_description="Test Goal"
    )
    dataset.record_decision(trace, outcome_success=True, execution_latency_ms=20.0, reward=1.0)

    summary = evaluator.evaluate_dataset(dataset)

    assert summary.total_decisions == 1
    assert summary.win_rate == 1.0

    current_weights = PlannerWeights(success_weight=0.45, latency_weight=0.15)
    tuned = trainer.tune_weights(summary, current_weights)

    # When win rate is 100%, success_weight decreases slightly and latency_weight increases
    assert tuned.latency_weight > current_weights.latency_weight


def test_deduplicating_cluster_compressor():
    """Verify DeduplicatingClusterCompressor filters out exact duplicate memory text before summary generation."""
    compressor = DeduplicatingClusterCompressor()

    item1 = IndexedMemoryItem(item_id="1", memory_type=MemoryType.EPISODIC, text="Duplicate Text")
    item2 = IndexedMemoryItem(item_id="2", memory_type=MemoryType.EPISODIC, text="Duplicate Text")
    item3 = IndexedMemoryItem(item_id="3", memory_type=MemoryType.SEMANTIC, text="Unique Text")

    ranked = [
        RankedMemoryItem(
            item=item1,
            relevance_score=0.8,
            recency_score=0.8,
            confidence_score=0.8,
            final_score=0.8,
        ),
        RankedMemoryItem(
            item=item2,
            relevance_score=0.8,
            recency_score=0.8,
            confidence_score=0.8,
            final_score=0.8,
        ),
        RankedMemoryItem(
            item=item3,
            relevance_score=0.9,
            recency_score=0.9,
            confidence_score=0.9,
            final_score=0.9,
        ),
    ]

    retained, summary = compressor.compress_memories(ranked)

    assert len(retained) == 2
    assert "Unique Text" in summary
