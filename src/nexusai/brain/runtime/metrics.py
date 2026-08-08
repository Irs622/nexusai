"""
TurnMetrics (v1.0 diagnostic telemetry) and TurnChunk (streaming delta) models.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from nexusai.brain.domain.version import SchemaVersion


@dataclass(frozen=True)
class TurnMetrics:
    """Immutable first-class diagnostic metrics artifact capturing turn performance.

    Attributes:
        metrics_version: Contract schema versioning.
        latency_ms: Total end-to-end turn execution latency in milliseconds.
        ttft_ms: Time To First Token in milliseconds (streaming latency).
        tokens_per_second: Throughput rate of generated tokens.
        provider_latency_ms: Downstream LLM provider execution time.
        input_tokens: Total input context tokens.
        output_tokens: Total output generated tokens.
        retry_count: Number of provider retries attempted.
        is_cancelled: True if turn was aborted by client cancellation.
        is_timeout: True if turn was aborted due to timeout policy.
    """

    metrics_version: SchemaVersion = field(default_factory=SchemaVersion)
    latency_ms: float = 0.0
    ttft_ms: float = 0.0
    tokens_per_second: float = 0.0
    provider_latency_ms: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    retry_count: int = 0
    is_cancelled: bool = False
    is_timeout: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Serialize TurnMetrics to dictionary format."""
        return {
            "metrics_version": self.metrics_version.to_dict(),
            "latency_ms": self.latency_ms,
            "ttft_ms": self.ttft_ms,
            "tokens_per_second": self.tokens_per_second,
            "provider_latency_ms": self.provider_latency_ms,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "retry_count": self.retry_count,
            "is_cancelled": self.is_cancelled,
            "is_timeout": self.is_timeout,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TurnMetrics:
        """Deserialize TurnMetrics from dictionary format."""
        version_data = data.get("metrics_version", {})
        metrics_version = (
            SchemaVersion.from_dict(version_data)
            if isinstance(version_data, dict)
            else SchemaVersion()
        )

        return cls(
            metrics_version=metrics_version,
            latency_ms=float(data.get("latency_ms", 0.0)),
            ttft_ms=float(data.get("ttft_ms", 0.0)),
            tokens_per_second=float(data.get("tokens_per_second", 0.0)),
            provider_latency_ms=float(data.get("provider_latency_ms", 0.0)),
            input_tokens=int(data.get("input_tokens", 0)),
            output_tokens=int(data.get("output_tokens", 0)),
            retry_count=int(data.get("retry_count", 0)),
            is_cancelled=bool(data.get("is_cancelled", False)),
            is_timeout=bool(data.get("is_timeout", False)),
        )


@dataclass(frozen=True)
class TurnChunk:
    """Enriched delta stream unit yielded directly to caller iterators.

    Attributes:
        delta: Incremental text slice generated in this chunk.
        finish_reason: Optional completion reason (e.g. "stop", "length").
        usage: Optional token usage dict attached to final chunk.
        sequence: Zero-indexed chunk sequence number.
        metadata: Optional additional stream metadata.
    """

    delta: str
    finish_reason: str | None = None
    usage: dict[str, int] | None = None
    sequence: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize TurnChunk to dictionary format."""
        return {
            "delta": self.delta,
            "finish_reason": self.finish_reason,
            "usage": self.usage,
            "sequence": self.sequence,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TurnChunk:
        """Deserialize TurnChunk from dictionary format."""
        return cls(
            delta=str(data.get("delta", "")),
            finish_reason=data.get("finish_reason"),
            usage=dict(data["usage"]) if data.get("usage") is not None else None,
            sequence=int(data.get("sequence", 0)),
            metadata=dict(data.get("metadata", {})),
        )
