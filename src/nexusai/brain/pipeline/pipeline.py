"""
ExecutionPipeline orchestrator executing ordered IExecutionStage implementations.
"""

from __future__ import annotations

from typing import Sequence

from nexusai.brain.pipeline.stages import (
    HistoryStage,
    IExecutionStage,
    PersistenceStage,
    PromptStage,
    ProviderStage,
)
from nexusai.brain.runtime.context import ExecutionContext
from nexusai.logging.logger import logger


class ExecutionPipeline:
    """Open/Closed execution pipeline executing an ordered sequence of IExecutionStage instances."""

    def __init__(self, stages: Sequence[IExecutionStage] | None = None) -> None:
        """Initialize ExecutionPipeline with a sequence of execution stages.

        Args:
            stages: Optional sequence of IExecutionStage implementations (defaults to standard pipeline).
        """
        self.stages: list[IExecutionStage] = (
            list(stages)
            if stages is not None
            else [
                HistoryStage(),
                PromptStage(),
                ProviderStage(),
                PersistenceStage(),
            ]
        )

    def add_stage(self, stage: IExecutionStage) -> None:
        """Add an execution stage to the pipeline (Open/Closed principle)."""
        self.stages.append(stage)

    async def process(self, ctx: ExecutionContext) -> None:
        """Process ExecutionContext sequentially through all configured stages.

        Args:
            ctx: Unified thread ExecutionContext.
        """
        logger.info(
            f"ExecutionPipeline starting processing ({len(self.stages)} stages) for execution '{ctx.runtime.execution_id}'"
        )

        for idx, stage in enumerate(self.stages, start=1):
            stage_name = stage.__class__.__name__
            logger.debug(f"Executing stage {idx}/{len(self.stages)}: {stage_name}")

            # Check cancellation token before executing stage
            if ctx.cancellation.is_cancelled:
                logger.warning(f"Pipeline cancelled before stage {stage_name}")
                break

            await stage.execute(ctx)

        logger.info(f"ExecutionPipeline completed for execution '{ctx.runtime.execution_id}'")
