"""CompactionResult delta container and SummaryBlock value object for NexusAI Context Compaction."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from nexusai.domain.models import Observation


@dataclass(frozen=True)
class SummaryBlock:
    """Immutable domain value object representing a generated context summary.

    Attributes:
        title: Short title description of compacted context.
        text: Detailed summary text content.
        observation_ids: Tuple of Observation ID strings covered in summary.
        created_at: Epoch timestamp float when summary block was created.
        version: Schema version string for backward compatibility.
    """

    title: str = "Context Summary"
    text: str = ""
    observation_ids: tuple[str, ...] = ()
    created_at: float = field(default_factory=time.time)
    version: str = "1.0"

    def __str__(self) -> str:
        if not self.text:
            return ""
        return f"{self.title}\n{self.text}"


@dataclass(frozen=True)
class CompactionResult:
    """Immutable delta output of a context compaction run.

    Attributes:
        retained_observations: List of active observations kept in working memory.
        compacted_observations: List of observations summarized during this run.
        discarded_observations: List of evicted observations pruned from context.
        summary_block: Generated SummaryBlock value object, or empty.
        units_freed: Estimated ContextUnits reclaimed by compaction.
    """

    retained_observations: list[Observation] = field(default_factory=list)
    compacted_observations: list[Observation] = field(default_factory=list)
    discarded_observations: list[Observation] = field(default_factory=list)
    summary_block: SummaryBlock = field(default_factory=SummaryBlock)
    units_freed: int = 0
