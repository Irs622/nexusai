"""
RetrievalContext, StageTrace, PipelineTrace, RetrievalStage middleware ABC, and QueryResult contracts.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
import json
from typing import Any, Sequence

from nexusai.memory.domain.record import MemoryRecord


@dataclass(frozen=True)
class StageTrace:
    """Telemetry trace container for an individual RetrievalStage execution."""

    stage_name: str
    input_count: int
    output_count: int
    latency_ms: float
    dropped_count: int
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert StageTrace to dictionary."""
        return asdict(self)


@dataclass
class PipelineTrace:
    """Telemetry trace container for an entire RetrievalPipeline run with export capabilities."""

    total_latency_ms: float = 0.0
    initial_count: int = 0
    final_count: int = 0
    stage_traces: list[StageTrace] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Export PipelineTrace as a python dictionary."""
        return {
            "total_latency_ms": self.total_latency_ms,
            "initial_count": self.initial_count,
            "final_count": self.final_count,
            "stage_traces": [
                st.to_dict() if hasattr(st, "to_dict") else str(st)
                for st in self.stage_traces
            ]
            if hasattr(self, "stage_traces")
            else [],
        }

    def to_json(self) -> str:
        """Export PipelineTrace as JSON string."""
        data = {
            "total_latency_ms": self.total_latency_ms,
            "initial_count": self.initial_count,
            "final_count": self.final_count,
            "stage_traces": [asdict(st) for st in self.stage_traces],
        }
        return json.dumps(data)

    def to_otel(self) -> list[dict[str, Any]]:
        """Export trace records formatted for OpenTelemetry span span_events."""
        spans = []
        for st in self.stage_traces:
            spans.append(
                {
                    "name": f"stage.{st.stage_name.lower()}",
                    "attributes": {
                        "stage.input_count": st.input_count,
                        "stage.output_count": st.output_count,
                        "stage.latency_ms": st.latency_ms,
                        "stage.dropped_count": st.dropped_count,
                    },
                }
            )
        return spans

    def pretty_print(self) -> str:
        """Return formatted clean text string representation of pipeline trace telemetry."""
        lines = [
            f"[TRACE] Pipeline Total Latency: {self.total_latency_ms:.2f}ms | In: {self.initial_count} | Out: {self.final_count}"
        ]
        for st in self.stage_traces:
            lines.append(
                f"  - [{st.stage_name}] in={st.input_count} out={st.output_count} dropped={st.dropped_count} ({st.latency_ms:.2f}ms)"
            )
        return "\n".join(lines)


@dataclass
class RetrievalContext:
    """Uniform middleware context passed through RetrievalStage pipeline."""

    query: str
    embedding: list[float] = field(default_factory=list)
    metadata_filters: dict[str, Any] = field(default_factory=dict)
    candidate_records: list[MemoryRecord] = field(default_factory=list)
    scores: dict[str, float] = field(default_factory=dict)
    sub_scores: dict[str, dict[str, float]] = field(default_factory=dict)
    trace_context: dict[str, Any] = field(default_factory=dict)
    stage_traces: list[StageTrace] = field(default_factory=list)


@dataclass(frozen=True)
class QueryResult:
    """Final output container of a memory query operation."""

    records: tuple[MemoryRecord, ...]
    scores: tuple[float, ...]
    formatted_context: str = ""
    trace: PipelineTrace | None = None


class RetrievalStage(ABC):
    """Abstract middleware stage for RetrievalPipeline processing."""

    @property
    def stage_name(self) -> str:
        """Return stage class name."""
        return self.__class__.__name__

    @abstractmethod
    async def execute(self, context: RetrievalContext) -> None:
        """Process and modify the uniform RetrievalContext in-place."""
        pass
