"""
Explicit Public Contract Serializers for Frozen API Surfaces.

Extracts ONLY stable public contract fields into deterministic JSON-serializable dictionaries.
Avoids internal private state, unstable object references, or non-deterministic ordering.
"""

from __future__ import annotations

from typing import Any

from nexusai.memory.contracts.embedding import EmbeddingCapabilities
from nexusai.memory.domain.record import MemoryRecord
from nexusai.providers.context import ExecutionContext
from nexusai.providers.models import ProviderHealth, ProviderMetadata
from nexusai.providers.profile import ProviderProfile


def serialize_provider_metadata(meta: ProviderMetadata) -> dict[str, Any]:
    """Serialize ProviderMetadata public contract."""
    return {
        "provider_id": meta.provider_id,
        "display_name": meta.display_name,
        "homepage": meta.homepage,
        "sdk_version": meta.sdk_version,
    }


def serialize_provider_health(health: ProviderHealth) -> dict[str, Any]:
    """Serialize ProviderHealth public contract."""
    return {
        "healthy": health.healthy,
        "latency_ms": health.latency_ms,
        "error": health.error,
        "available_models": health.available_models,
    }


def serialize_provider_profile(profile: ProviderProfile) -> dict[str, Any]:
    """Serialize ProviderProfile public contract."""
    return {
        "provider_id": profile.provider_id,
        "metadata": serialize_provider_metadata(profile.metadata),
        "metrics_confidence": round(profile.metrics_confidence, 2),
    }


def serialize_embedding_capabilities(caps: EmbeddingCapabilities) -> dict[str, Any]:
    """Serialize EmbeddingCapabilities public contract."""
    return {
        "model_name": caps.model_name,
        "dimensions": caps.dimensions,
        "max_batch": caps.max_batch,
        "distance_metric": caps.distance_metric,
        "normalized_output": caps.normalized_output,
        "supports_batch": caps.supports_batch,
    }


def serialize_memory_record(record: MemoryRecord) -> dict[str, Any]:
    """Serialize MemoryRecord public contract."""
    return {
        "id": record.id,
        "schema_version": record.schema_version,
        "memory_type": record.memory_type.value,
        "scope": record.scope.value,
        "raw_text": record.content.raw_text,
        "summary": record.content.summary,
        "source": record.metadata.source,
        "tags": sorted(list(record.metadata.tags)),
    }


def serialize_execution_context(ctx: ExecutionContext) -> dict[str, Any]:
    """Serialize ExecutionContext public contract."""
    return {
        "request_id": ctx.request.request_id,
        "trace_id": ctx.trace.trace_id,
        "model": ctx.runtime.model,
        "is_cancelled": ctx.runtime.cancellation_token.is_cancelled,
    }
