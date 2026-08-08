"""
Immutable RetrievalPipeline executing stages with StageTrace and PipelineTrace telemetry.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Sequence

from nexusai.memory.contracts.retrieval import (
    PipelineTrace,
    QueryResult,
    RetrievalContext,
    RetrievalStage,
    StageTrace,
)


@dataclass(frozen=True)
class RetrievalPipelineConfig:
    """Immutable configuration descriptor for RetrievalPipeline."""

    max_candidates: int = 50
    cutoff_score: float = 0.0
    enabled_stages: tuple[str, ...] = field(default_factory=tuple)
    weights: dict[str, float] = field(default_factory=dict)
    ranking_parameters: dict[str, Any] = field(default_factory=dict)


class RetrievalPipeline:
    """Immutable execution pipeline holding a frozen sequence of RetrievalStage middleware with telemetry."""

    def __init__(
        self, stages: Sequence[RetrievalStage], config: RetrievalPipelineConfig | None = None
    ) -> None:
        self._stages: tuple[RetrievalStage, ...] = tuple(stages)
        self._config: RetrievalPipelineConfig = config or RetrievalPipelineConfig()

    @property
    def config(self) -> RetrievalPipelineConfig:
        """Return pipeline configuration."""
        return self._config

    @property
    def stages(self) -> tuple[RetrievalStage, ...]:
        """Return frozen tuple of retrieval stages."""
        return self._stages

    async def execute(self, context: RetrievalContext) -> QueryResult:
        """Execute middleware stages sequentially with StageTrace telemetry."""
        pipeline_start = time.time()
        initial_count = len(context.candidate_records)
        stage_traces: list[StageTrace] = []

        # Pass pipeline weights via trace_context
        if self._config.weights:
            context.trace_context["pipeline_weights"] = self._config.weights

        for stage in self._stages:
            stage_start = time.time()
            in_cnt = len(context.candidate_records)

            await stage.execute(context)

            stage_latency = (time.time() - stage_start) * 1000.0
            out_cnt = len(context.candidate_records)
            dropped = max(0, in_cnt - out_cnt)

            trace_item = StageTrace(
                stage_name=stage.stage_name,
                input_count=in_cnt,
                output_count=out_cnt,
                latency_ms=stage_latency,
                dropped_count=dropped,
            )
            stage_traces.append(trace_item)
            context.stage_traces.append(trace_item)

        # Build final QueryResult
        sorted_records = list(context.candidate_records)
        scores_list = [context.scores.get(r.id, 0.5) for r in sorted_records]

        # Filter by cutoff_score
        filtered_records = []
        filtered_scores = []
        for r, s in zip(sorted_records, scores_list):
            if s >= self._config.cutoff_score:
                filtered_records.append(r)
                filtered_scores.append(s)

        final_records = tuple(filtered_records[: self._config.max_candidates])
        final_scores = tuple(filtered_scores[: self._config.max_candidates])

        total_latency = (time.time() - pipeline_start) * 1000.0
        pipeline_trace = PipelineTrace(
            total_latency_ms=total_latency,
            initial_count=initial_count,
            final_count=len(final_records),
            stage_traces=stage_traces,
        )

        return QueryResult(records=final_records, scores=final_scores, trace=pipeline_trace)
