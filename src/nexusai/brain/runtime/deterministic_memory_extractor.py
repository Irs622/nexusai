"""Deterministic memory extractor identifying candidate memories from execution observations."""

from __future__ import annotations

from typing import Sequence

from nexusai.brain.domain.agent_loop import Observation
from nexusai.brain.domain.memory import MemoryType, PrivacyLevel
from nexusai.brain.domain.memory_learning import (
    MemoryCandidate,
    MemoryExtractionResult,
)
from nexusai.brain.ports.memory_learning_port import IMemoryExtractor


class DeterministicMemoryExtractor(IMemoryExtractor):
    """Deterministic extractor identifying episodic execution outcomes and explicit preference candidates."""

    async def extract(
        self,
        *,
        session_id: str,
        execution_id: str,
        observations: Sequence[Observation],
        user_prompt: str,
    ) -> MemoryExtractionResult:
        """Identify candidate memory entries from execution results."""
        candidates: list[MemoryCandidate] = []
        discarded_cnt = 0

        # 1. Extract Episodic Memory from Observation Results
        for obs in observations:
            successful_outputs = [r.output for r in obs.node_results if r.success and r.output]
            failed_errors = [r.error_message for r in obs.node_results if not r.success and r.error_message]

            if successful_outputs:
                summary_content = f"Execution iteration {obs.iteration} succeeded: {'; '.join(successful_outputs)}"
                candidates.append(
                    MemoryCandidate(
                        content=summary_content,
                        memory_type=MemoryType.EPISODIC,
                        confidence=1.0,
                        source_type="agent_execution_observation",
                        source_id=f"{execution_id}-obs-{obs.iteration}",
                        session_id=session_id,
                        execution_id=execution_id,
                    )
                )

            if failed_errors:
                err_content = f"Execution iteration {obs.iteration} failed: {'; '.join(failed_errors)}"
                candidates.append(
                    MemoryCandidate(
                        content=err_content,
                        memory_type=MemoryType.EPISODIC,
                        confidence=0.95,
                        source_type="agent_execution_error",
                        source_id=f"{execution_id}-err-{obs.iteration}",
                        session_id=session_id,
                        execution_id=execution_id,
                    )
                )

        # 2. Extract Semantic Preference Candidates from Explicit Statements
        low_prompt = user_prompt.lower()
        if "prefer" in low_prompt or "always use" in low_prompt or "must use" in low_prompt:
            candidates.append(
                MemoryCandidate(
                    content=f"User preference constraint: {user_prompt.strip()}",
                    memory_type=MemoryType.SEMANTIC,
                    confidence=0.90,
                    source_type="user_explicit_statement",
                    source_id=f"{execution_id}-user-pref",
                    session_id=session_id,
                    execution_id=execution_id,
                )
            )

        return MemoryExtractionResult(
            candidates=tuple(candidates),
            discarded_count=discarded_cnt,
            reason="Deterministic extraction complete",
        )
