"""
MemoryEngineConfig unified configuration container.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class MemoryEngineConfig:
    """Unified configuration dataclass for NexusAI Memory Engine."""

    storage_dir: str = ".nexusai/memory/storage"
    sqlite_db_name: str = "memory_records.db"
    vector_provider: str = "in_memory"
    vector_dimensions: int = 768
    vector_collection_name: str = "nexusai_memory_vectors"
    embedding_provider: str = "mock"
    embedding_model: str = "nomic-embed-text"
    pipeline_profile: str = "brain_profile"
    cutoff_score: float = 0.0
    max_candidates: int = 50
    outbox_batch_size: int = 20
    outbox_max_retries: int = 3
    pipeline_weights: dict[str, float] = field(
        default_factory=lambda: {
            "similarity": 0.7,
            "recency": 0.2,
            "importance": 0.1,
        }
    )

    def get_sqlite_db_path(self) -> Path:
        """Return resolved SQLite database Path object."""
        p = Path(self.storage_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p / self.sqlite_db_name
