"""DecisionDataset for accumulating decision trace logs for offline strategy evaluation and RL training."""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from nexusai.brain.domain.agent import ActionCandidate, DecisionTrace


@dataclass(frozen=True)
class DecisionDatasetEntry:
    """Individual enriched decision trace entry recorded for offline dataset evaluation & RL training.

    Attributes:
        entry_id: Unique entry UUID string.
        session_id: Session UUID string.
        context_hash: Hash of context state.
        candidates: Tuple of evaluated ActionCandidate objects.
        chosen_action: Selected action name.
        outcome_success: Boolean outcome flag.
        execution_latency_ms: Execution duration in ms.
        environment_metadata: Map of OS, Python version, git SHA metadata.
        provider_version: Vendor provider version string.
        model_version: LLM model identifier string.
        capability_hash: SHA-256 hash of active capability graph.
        state_hash: SHA-256 state hash of WorkingMemory.
        reward: Scalar RL reward signal.
        user_feedback: Optional human user feedback rating string.
        timestamp: Epoch timestamp float.
    """

    entry_id: str
    session_id: str
    context_hash: str
    candidates: tuple[ActionCandidate, ...]
    chosen_action: str
    outcome_success: bool = True
    execution_latency_ms: float = 0.0
    environment_metadata: dict[str, str] = field(default_factory=dict)
    provider_version: str = "v1.0"
    model_version: str = "mock-v1"
    capability_hash: str = ""
    state_hash: str = ""
    reward: float = 1.0
    user_feedback: str = "PASS"
    timestamp: float = field(default_factory=time.time)


class DecisionDataset:
    """Accumulates decision trace entries for offline strategy evaluation and RL dataset training."""

    def __init__(self, dataset_name: str = "nexusai-decision-dataset-v1") -> None:
        self.dataset_name = dataset_name
        self.entries: list[DecisionDatasetEntry] = []

    def record_decision(
        self,
        trace: DecisionTrace,
        outcome_success: bool = True,
        execution_latency_ms: float = 0.0,
        reward: float = 1.0,
        user_feedback: str = "PASS",
    ) -> DecisionDatasetEntry:
        """Record a DecisionTrace as an enriched DecisionDatasetEntry."""
        entry = DecisionDatasetEntry(
            entry_id=trace.trace_id,
            session_id=trace.session_id,
            context_hash=f"ctx-{len(trace.goal_description)}",
            candidates=trace.candidate_rankings,
            chosen_action=trace.outcome.chosen_action,
            outcome_success=outcome_success,
            execution_latency_ms=execution_latency_ms,
            environment_metadata={"os": "Darwin", "git_commit": "HEAD"},
            provider_version="v1.0",
            model_version="mock-v1",
            capability_hash="cap-hash-v1",
            state_hash="state-hash-v1",
            reward=reward,
            user_feedback=user_feedback,
        )
        self.entries.append(entry)
        return entry

    def save_jsonl(self, file_path: Path | str) -> None:
        """Save DecisionDataset entries to JSONL file."""
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = [json.dumps(asdict(e)) for e in self.entries]
        path.write_text("\n".join(lines), encoding="utf-8")
