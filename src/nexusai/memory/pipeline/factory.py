"""
PipelineFactory for profile-based immutable RetrievalPipeline instantiation.
"""

from __future__ import annotations

from typing import Sequence

from nexusai.memory.contracts.retrieval import RetrievalStage
from nexusai.memory.pipeline.builder import PipelineBuilder
from nexusai.memory.pipeline.retrieval_pipeline import RetrievalPipeline, RetrievalPipelineConfig


class PipelineFactory:
    """Factory creating profile-based immutable RetrievalPipeline instances."""

    def __init__(self) -> None:
        self._profiles: dict[str, tuple[RetrievalStage, ...]] = {}
        self._configs: dict[str, RetrievalPipelineConfig] = {}

    def register_profile(
        self,
        profile_name: str,
        stages: Sequence[RetrievalStage],
        config: RetrievalPipelineConfig | None = None,
    ) -> None:
        """Register a pipeline profile by name."""
        self._profiles[profile_name] = tuple(stages)
        self._configs[profile_name] = config or RetrievalPipelineConfig()

    def create_pipeline(self, profile_name: str = "default") -> RetrievalPipeline:
        """Construct an immutable RetrievalPipeline for target profile."""
        stages = self._profiles.get(profile_name, ())
        config = self._configs.get(profile_name, RetrievalPipelineConfig())

        builder = PipelineBuilder(config)
        builder.add_stages(stages)
        return builder.build()
