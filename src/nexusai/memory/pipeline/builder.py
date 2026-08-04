"""
PipelineBuilder for constructing immutable RetrievalPipeline instances during bootstrap.
"""

from __future__ import annotations

from typing import Sequence

from nexusai.memory.contracts.retrieval import RetrievalStage
from nexusai.memory.pipeline.retrieval_pipeline import RetrievalPipeline, RetrievalPipelineConfig


class PipelineBuilder:
    """Builder for constructing immutable RetrievalPipeline instances during system bootstrap."""

    def __init__(self, config: RetrievalPipelineConfig | None = None) -> None:
        self._config = config or RetrievalPipelineConfig()
        self._stages: list[RetrievalStage] = []

    def set_config(self, config: RetrievalPipelineConfig) -> PipelineBuilder:
        """Set pipeline configuration."""
        self._config = config
        return self

    def add_stage(self, stage: RetrievalStage) -> PipelineBuilder:
        """Add a RetrievalStage middleware to the builder queue."""
        self._stages.append(stage)
        return self

    def add_stages(self, stages: Sequence[RetrievalStage]) -> PipelineBuilder:
        """Add multiple RetrievalStage middleware instances."""
        self._stages.extend(stages)
        return self

    def build(self) -> RetrievalPipeline:
        """Construct and return an immutable RetrievalPipeline instance."""
        return RetrievalPipeline(stages=tuple(self._stages), config=self._config)
