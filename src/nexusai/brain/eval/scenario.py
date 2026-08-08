"""Golden Scenario Dataset abstractions for Agent Quality Evaluation."""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Scenario:
    """Immutable golden benchmark scenario definition.

    Attributes:
        scenario_id: Unique scenario UUID or slug string.
        description: Detailed scenario goal description.
        user_request: Original user prompt text.
        category: Benchmark category (TOOL, RECOVERY, PLANNING, REFLECTION, COMPACTION).
        difficulty: Difficulty level string (EASY, MEDIUM, HARD).
        tags: Tuple of tags for filtering.
        expected_tools: Tuple of tool names expected to be invoked.
        expected_observations: Tuple of expected observation payloads or patterns.
        expected_summary: Expected summary text pattern.
        expected_decision: Expected final agent decision (e.g. COMPLETE, REPLAN).
        expected_hash: Expected SHA-256 state hash string.
        timeout_sec: Maximum execution timeout in seconds.
        max_turns: Maximum turn iteration ceiling.
    """

    scenario_id: str
    description: str
    user_request: str
    category: str = "GENERAL"
    difficulty: str = "MEDIUM"
    tags: tuple[str, ...] = ()
    expected_tools: tuple[str, ...] = ()
    expected_observations: tuple[str, ...] = ()
    expected_summary: str = ""
    expected_decision: str = "COMPLETE"
    expected_hash: str = ""
    timeout_sec: float = 30.0
    max_turns: int = 10

    def to_dict(self) -> dict[str, Any]:
        """Convert Scenario to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Scenario:
        """Construct Scenario from dictionary."""
        return cls(
            scenario_id=data["scenario_id"],
            description=data.get("description", ""),
            user_request=data.get("user_request", ""),
            category=data.get("category", "GENERAL"),
            difficulty=data.get("difficulty", "MEDIUM"),
            tags=tuple(data.get("tags", [])),
            expected_tools=tuple(data.get("expected_tools", [])),
            expected_observations=tuple(data.get("expected_observations", [])),
            expected_summary=data.get("expected_summary", ""),
            expected_decision=data.get("expected_decision", "COMPLETE"),
            expected_hash=data.get("expected_hash", ""),
            timeout_sec=data.get("timeout_sec", 30.0),
            max_turns=data.get("max_turns", 10),
        )


@dataclass(frozen=True)
class ScenarioCorpus:
    """Collection container managing a dataset of golden benchmark scenarios with version metadata.

    Attributes:
        corpus_name: Unique corpus dataset name (e.g. "nexusai-golden-v1").
        version: Integer dataset version (default 1).
        created_at: ISO timestamp or string timestamp when corpus was generated.
        generator: Generator tool name string.
        scenarios: Tuple of Scenario items.
    """

    corpus_name: str
    version: int = 1
    created_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ"))
    generator: str = "NexusAI Golden Dataset Generator"
    scenarios: tuple[Scenario, ...] = ()

    def save_json(self, file_path: Path | str) -> None:
        """Save scenario corpus to JSON dataset file with metadata."""
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "corpus_name": self.corpus_name,
            "version": self.version,
            "created_at": self.created_at,
            "generator": self.generator,
            "count": len(self.scenarios),
            "scenarios": [s.to_dict() for s in self.scenarios],
        }
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    @classmethod
    def load_json(cls, file_path: Path | str) -> ScenarioCorpus:
        """Load scenario corpus from JSON dataset file."""
        path = Path(file_path)
        data = json.loads(path.read_text(encoding="utf-8"))
        scenarios = [Scenario.from_dict(item) for item in data.get("scenarios", [])]
        return cls(
            corpus_name=data.get("corpus_name", "default-corpus"),
            version=int(data.get("version", 1)),
            created_at=data.get("created_at", ""),
            generator=data.get("generator", "NexusAI Golden Dataset Generator"),
            scenarios=tuple(scenarios),
        )
