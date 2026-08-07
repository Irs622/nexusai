"""
ExecutionTracer telemetry engine and OpenTelemetry span context helpers.
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Generator

from nexusai.brain.domain.version import SchemaVersion
from nexusai.brain.runtime.metrics import TurnMetrics
from nexusai.logging.logger import logger


@dataclass
class ExecutionTracer:
    """Telemetry engine capturing stage timestamps, TTFT, throughput, and OpenTelemetry spans.

    Per-execution instance lifecycle (never a shared singleton).
    Sub-stage latency milestones tracked:
        - request_start_time: Turn request received.
        - provider_connected_time: Network connection established to provider.
        - first_chunk_time: First token chunk received (TTFT marker).
        - last_chunk_time: Last token chunk received (stream finished).
    """

    request_start_time: float = field(default_factory=time.perf_counter)
    provider_connected_time: float | None = None
    first_chunk_time: float | None = None
    last_chunk_time: float | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    retry_count: int = 0
    is_cancelled: bool = False
    is_timeout: bool = False

    def mark_provider_connected(self) -> None:
        """Mark provider connection established timestamp."""
        if self.provider_connected_time is None:
            self.provider_connected_time = time.perf_counter()

    def mark_first_chunk(self) -> None:
        """Mark first token chunk received (TTFT timestamp)."""
        if self.first_chunk_time is None:
            self.first_chunk_time = time.perf_counter()
            logger.debug(f"TTFT marker captured: {self.calculated_ttft_ms:.2f} ms")

    def mark_last_chunk(self) -> None:
        """Mark stream completion timestamp."""
        self.last_chunk_time = time.perf_counter()

    @property
    def calculated_ttft_ms(self) -> float:
        """Calculate Time To First Token in milliseconds."""
        if self.first_chunk_time is None:
            return 0.0
        return (self.first_chunk_time - self.request_start_time) * 1000.0

    @property
    def calculated_latency_ms(self) -> float:
        """Calculate total end-to-end turn latency in milliseconds."""
        end_time = self.last_chunk_time or time.perf_counter()
        return (end_time - self.request_start_time) * 1000.0

    @property
    def calculated_provider_latency_ms(self) -> float:
        """Calculate downstream provider execution latency in milliseconds."""
        start = self.provider_connected_time or self.request_start_time
        end = self.last_chunk_time or time.perf_counter()
        return (end - start) * 1000.0

    @property
    def calculated_tokens_per_second(self) -> float:
        """Calculate token throughput rate based purely on streaming duration (output tokens / streaming duration)."""
        if self.output_tokens <= 0 or self.first_chunk_time is None:
            return 0.0
        gen_end = self.last_chunk_time or time.perf_counter()
        streaming_duration_sec = gen_end - self.first_chunk_time
        if streaming_duration_sec <= 0.0:
            return 0.0
        return self.output_tokens / streaming_duration_sec

    def finalize_metrics(self) -> TurnMetrics:
        """Construct immutable TurnMetrics v1.0 domain payload."""
        if self.last_chunk_time is None:
            self.last_chunk_time = time.perf_counter()

        metrics = TurnMetrics(
            metrics_version=SchemaVersion(1, 0),
            latency_ms=self.calculated_latency_ms,
            ttft_ms=self.calculated_ttft_ms,
            tokens_per_second=self.calculated_tokens_per_second,
            provider_latency_ms=self.calculated_provider_latency_ms,
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
            retry_count=self.retry_count,
            is_cancelled=self.is_cancelled,
            is_timeout=self.is_timeout,
        )
        logger.info(
            f"TurnMetrics finalized: TTFT={metrics.ttft_ms:.2f}ms, Total={metrics.latency_ms:.2f}ms, "
            f"Throughput={metrics.tokens_per_second:.1f} tok/s"
        )
        return metrics

    @contextmanager
    def span(self, span_name: str, attributes: dict[str, Any] | None = None) -> Generator[None, None, None]:
        """OpenTelemetry-compatible span context manager helper."""
        span_start = time.perf_counter()
        logger.debug(f"[SPAN START] {span_name}", extra=attributes or {})
        try:
            yield
        finally:
            elapsed_ms = (time.perf_counter() - span_start) * 1000.0
            logger.debug(f"[SPAN END] {span_name} ({elapsed_ms:.2f} ms)")
