"""Unit test suite for P3-5 Memory Learning domain models, candidate validation, policy decisions, and fingerprinting."""

from __future__ import annotations

import asyncio
import pytest

from nexusai.brain.domain.memory import MemoryType, PrivacyLevel
from nexusai.brain.domain.memory_learning import (
    MemoryCandidate,
    MemoryPromotionDecision,
    compute_memory_fingerprint,
)
from nexusai.brain.runtime.memory_learning_policy import MemoryLearningPolicy


def test_memory_candidate_domain_validation_and_secret_redaction() -> None:
    """Test MemoryCandidate domain validation rules and secret redaction."""
    cand = MemoryCandidate(
        content="Execution outcome noted",
        memory_type=MemoryType.EPISODIC,
        confidence=0.9,
        source_type="execution_observation",
        source_id="obs-1",
        session_id="sess-1",
        metadata={"user": "alice", "api_key": "secret-12345"},
    )

    assert cand.content == "Execution outcome noted"
    assert cand.confidence == 0.9
    assert cand.metadata["user"] == "alice"
    assert cand.metadata["api_key"] == "[REDACTED_SECRET]"

    with pytest.raises(ValueError, match="content cannot be empty"):
        MemoryCandidate(
            content="  ",
            memory_type=MemoryType.EPISODIC,
            confidence=0.9,
            source_type="test",
            source_id="1",
            session_id="sess-1",
        )

    with pytest.raises(ValueError, match="confidence must be between 0.0 and 1.0"):
        MemoryCandidate(
            content="Content",
            memory_type=MemoryType.EPISODIC,
            confidence=1.5,
            source_type="test",
            source_id="1",
            session_id="sess-1",
        )


def test_memory_fingerprint_determinism() -> None:
    """Test compute_memory_fingerprint produces canonical hashes regardless of string whitespace casing."""
    fp1 = compute_memory_fingerprint("sess-1", MemoryType.SEMANTIC, "User prefers Python 3.12")
    fp2 = compute_memory_fingerprint("sess-1", MemoryType.SEMANTIC, "user  PREFERS   python 3.12")

    assert fp1 == fp2, "Canonical memory fingerprints must match for equivalent normalized content"


@pytest.mark.asyncio
async def test_memory_learning_policy_decisions() -> None:
    """Test MemoryLearningPolicy decision thresholds."""
    policy = MemoryLearningPolicy(semantic_confidence_threshold=0.85)

    # 1. WORKING -> DISCARD
    c_work = MemoryCandidate("work", MemoryType.WORKING, 1.0, "test", "1", "sess-1")
    assert await policy.decide(c_work) == MemoryPromotionDecision.DISCARD

    # 2. EPISODIC -> STORE_EPISODIC
    c_epi = MemoryCandidate("epi", MemoryType.EPISODIC, 1.0, "test", "1", "sess-1")
    assert await policy.decide(c_epi) == MemoryPromotionDecision.STORE_EPISODIC

    # 3. SEMANTIC with confidence=0.90 -> PROMOTE_SEMANTIC
    c_sem_high = MemoryCandidate("sem", MemoryType.SEMANTIC, 0.90, "test", "1", "sess-1")
    assert await policy.decide(c_sem_high) == MemoryPromotionDecision.PROMOTE_SEMANTIC

    # 4. SEMANTIC with confidence=0.70 < 0.85 threshold -> DISCARD
    c_sem_low = MemoryCandidate("sem", MemoryType.SEMANTIC, 0.70, "test", "1", "sess-1")
    assert await policy.decide(c_sem_low) == MemoryPromotionDecision.DISCARD


if __name__ == "__main__":
    test_memory_candidate_domain_validation_and_secret_redaction()
    test_memory_fingerprint_determinism()
    asyncio.run(test_memory_learning_policy_decisions())
    print("ALL P3-5 AGENT MEMORY LEARNING UNIT TESTS PASSED SUCCESSFULLY!")
