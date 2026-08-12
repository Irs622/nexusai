"""MemoryLifecycle composition layer orchestrating pre-planning context retrieval and post-execution episodic learning."""

from __future__ import annotations

import time
from typing import Any, Sequence

from nexusai.brain.domain.agent_loop import Observation
from nexusai.brain.domain.memory import (
    MemoryEntry,
    MemoryProvenance,
    MemoryType,
)
from nexusai.brain.domain.memory_learning import (
    MemoryCandidate,
    MemoryLearningResult,
    MemoryPromotionDecision,
    compute_memory_fingerprint,
)
from nexusai.brain.domain.observability import RuntimeEvent, RuntimeEventType
from nexusai.brain.ports.memory_learning_port import (
    IMemoryExtractor,
    IMemoryLearningPolicy,
    IMemoryLifecycle,
)
from nexusai.brain.ports.memory_port import IContextBuilder, IMemoryRetriever, IMemoryStore
from nexusai.brain.ports.observability_port import IObservabilityPort
from nexusai.brain.runtime.deterministic_memory_extractor import DeterministicMemoryExtractor
from nexusai.brain.runtime.memory_learning_policy import MemoryLearningPolicy


class MemoryLifecycle(IMemoryLifecycle):
    """Composition runtime layer coordinating pre-planning retrieval and post-execution memory learning."""

    def __init__(
        self,
        memory_store: IMemoryStore,
        retriever: IMemoryRetriever,
        context_builder: IContextBuilder,
        extractor: IMemoryExtractor | None = None,
        policy: IMemoryLearningPolicy | None = None,
        telemetry: IObservabilityPort | None = None,
    ) -> None:
        self.memory_store = memory_store
        self.retriever = retriever
        self.context_builder = context_builder
        self.extractor = extractor or DeterministicMemoryExtractor()
        self.policy = policy or MemoryLearningPolicy()
        self.telemetry = telemetry

    async def _safe_telemetry_event(
        self,
        event_type: RuntimeEventType,
        session_id: str,
        execution_id: str | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> None:
        if not self.telemetry:
            return
        try:
            now = time.time()
            evt = RuntimeEvent(
                event_id=f"mem-lc-{int(now * 1000)}",
                event_type=event_type,
                timestamp=now,
                execution_id=execution_id,
                attributes={"session_id": session_id, **(attributes or {})},
            )
            await self.telemetry.emit_event(evt)
        except Exception:
            pass

    async def retrieve_context(
        self,
        *,
        session_id: str,
        query_text: str,
    ) -> str:
        """Retrieve bounded context for planning input strictly enforcing session isolation."""
        try:
            context_text, _ = await self.context_builder.build_context(
                session_id=session_id,
                query_text=query_text,
                max_tokens=4096,
            )
            return context_text
        except Exception as err:
            await self._safe_telemetry_event(
                RuntimeEventType.EXECUTION_FAILED,
                session_id=session_id,
                attributes={"error": f"Memory context retrieval failed: {err}"},
            )
            return ""

    async def learn_from_execution(
        self,
        *,
        session_id: str,
        execution_id: str,
        user_prompt: str,
        observations: Sequence[Observation],
    ) -> MemoryLearningResult:
        """Extract, evaluate, and persist episodic memory and qualified semantic memory candidates."""
        stored = 0
        promoted = 0
        invalidated = 0
        discarded = 0

        try:
            extraction = await self.extractor.extract(
                session_id=session_id,
                execution_id=execution_id,
                observations=observations,
                user_prompt=user_prompt,
            )

            seen_fingerprints: set[str] = set()

            for candidate in extraction.candidates:
                # 1. Deduplication Check via SHA-256 Memory Fingerprint
                fingerprint = compute_memory_fingerprint(session_id, candidate.memory_type, candidate.content)
                if fingerprint in seen_fingerprints:
                    discarded += 1
                    continue
                seen_fingerprints.add(fingerprint)

                # 2. Evaluate Decision via MemoryLearningPolicy
                decision = await self.policy.decide(candidate)

                if decision == MemoryPromotionDecision.DISCARD:
                    discarded += 1
                    continue

                prov = MemoryProvenance(
                    source_type=candidate.source_type,
                    source_id=candidate.source_id,
                    confidence=candidate.confidence,
                    version=1,
                )

                if decision == MemoryPromotionDecision.STORE_EPISODIC:
                    mem_id = f"mem-epi-{execution_id}-{stored}"
                    entry = MemoryEntry(
                        memory_id=mem_id,
                        session_id=session_id,
                        execution_id=execution_id,
                        memory_type=MemoryType.EPISODIC,
                        content=candidate.content,
                        provenance=prov,
                        privacy_level=candidate.privacy_level,
                        metadata=candidate.metadata,
                    )
                    await self.memory_store.store(entry)
                    stored += 1

                elif decision == MemoryPromotionDecision.PROMOTE_SEMANTIC:
                    # Check existing semantic memories for contradiction / update invalidation
                    existing_semantic = await self.memory_store.list_session_memories(session_id, memory_type=MemoryType.SEMANTIC)
                    for old_mem in existing_semantic:
                        if old_mem.content.split(":")[0] == candidate.content.split(":")[0]:
                            await self.memory_store.invalidate(old_mem.memory_id, session_id)
                            invalidated += 1

                    mem_id = f"mem-sem-{execution_id}-{promoted}"
                    entry = MemoryEntry(
                        memory_id=mem_id,
                        session_id=session_id,
                        execution_id=execution_id,
                        memory_type=MemoryType.SEMANTIC,
                        content=candidate.content,
                        provenance=prov,
                        privacy_level=candidate.privacy_level,
                        metadata=candidate.metadata,
                    )
                    await self.memory_store.store(entry)
                    promoted += 1

            return MemoryLearningResult(
                stored_count=stored,
                promoted_count=promoted,
                invalidated_count=invalidated,
                discarded_count=discarded + extraction.discarded_count,
            )
        except Exception as err:
            await self._safe_telemetry_event(
                RuntimeEventType.EXECUTION_FAILED,
                session_id=session_id,
                execution_id=execution_id,
                attributes={"error": f"Memory learning failed: {err}"},
            )
            return MemoryLearningResult(
                stored_count=stored,
                promoted_count=promoted,
                invalidated_count=invalidated,
                discarded_count=discarded,
            )
