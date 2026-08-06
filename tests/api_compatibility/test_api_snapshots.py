"""
API Compatibility Golden Snapshot Test Suite.

Verifies that frozen public API surfaces maintain backward compatibility.
Fails if public contract serialization changes without explicit --update-snapshots.
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from nexusai.memory.contracts.embedding import EmbeddingCapabilities
from nexusai.memory.domain.content import MemoryContent
from nexusai.memory.domain.metadata import MemoryMetadata
from nexusai.memory.domain.record import MemoryRecord, MemoryScope, MemoryType
from nexusai.providers.context import ExecutionContext
from nexusai.providers.models import ProviderCapabilities, ProviderHealth, ProviderMetadata
from nexusai.providers.profile import ProviderProfile

from tests.api_compatibility.serializers import (
    serialize_embedding_capabilities,
    serialize_execution_context,
    serialize_memory_record,
    serialize_provider_health,
    serialize_provider_metadata,
    serialize_provider_profile,
)

pytestmark = pytest.mark.snapshot
SNAPSHOT_DIR = Path(__file__).parent / "golden"


def _check_snapshot(name: str, actual_dict: dict, request: pytest.FixtureRequest) -> None:
    """Compare serialized object dict with golden snapshot file on disk."""
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    snapshot_path = SNAPSHOT_DIR / f"{name}.json"
    update_mode = request.config.getoption("--update-snapshots", default=False)

    formatted_json = json.dumps(actual_dict, indent=2, sort_keys=True)

    if update_mode or not snapshot_path.exists():
        snapshot_path.write_text(formatted_json, encoding="utf-8")
        print(f"\n📸 Updated golden snapshot: {snapshot_path}")
        return

    expected_json = snapshot_path.read_text(encoding="utf-8")
    assert formatted_json == expected_json, (
        f"API Compatibility Golden Snapshot mismatch for '{name}'!\n"
        f"Path: {snapshot_path}\n"
        f"Run 'pytest tests/api_compatibility/ --update-snapshots' if this change is an intentional ADR-approved API evolution."
    )


def conftest_options(parser: pytest.Parser) -> None:
    """Add --update-snapshots flag to pytest."""
    pass


def test_provider_metadata_snapshot(request: pytest.FixtureRequest) -> None:
    meta = ProviderMetadata(
        provider_id="openrouter",
        display_name="OpenRouter API",
        homepage="https://openrouter.ai",
        sdk_version="1.0.0",
    )
    _check_snapshot("provider_metadata", serialize_provider_metadata(meta), request)


def test_provider_health_snapshot(request: pytest.FixtureRequest) -> None:
    health = ProviderHealth(
        healthy=True,
        latency_ms=45.2,
        error=None,
        available_models=12,
    )
    _check_snapshot("provider_health", serialize_provider_health(health), request)


def test_provider_profile_snapshot(request: pytest.FixtureRequest) -> None:
    meta = ProviderMetadata(provider_id="anthropic", display_name="Anthropic Claude Engine")
    prof = ProviderProfile(metadata=meta)
    _check_snapshot("provider_profile", serialize_provider_profile(prof), request)


def test_embedding_capabilities_snapshot(request: pytest.FixtureRequest) -> None:
    caps = EmbeddingCapabilities(
        model_name="ollama/nomic-embed-text",
        dimensions=768,
        max_batch=64,
        distance_metric="cosine",
        normalized_output=True,
        supports_batch=True,
    )
    _check_snapshot("embedding_capabilities", serialize_embedding_capabilities(caps), request)


def test_memory_record_snapshot(request: pytest.FixtureRequest) -> None:
    record = MemoryRecord(
        id="rec_golden_001",
        schema_version="1.0.0",
        memory_type=MemoryType.EPISODIC,
        scope=MemoryScope.SESSION,
        content=MemoryContent(raw_text="User requested plugin installation.", summary="Plugin install request"),
        metadata=MemoryMetadata(source="user_prompt", tags=["plugins", "setup"]),
    )
    _check_snapshot("memory_record", serialize_memory_record(record), request)


def test_execution_context_snapshot(request: pytest.FixtureRequest) -> None:
    ctx = ExecutionContext()
    ctx.request.request_id = "req_12345"
    ctx.trace.trace_id = "tr_67890"
    ctx.runtime.model = "gpt-4o"
    _check_snapshot("execution_context", serialize_execution_context(ctx), request)
