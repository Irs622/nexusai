"""
Unit tests for Milestone 2.4.3: Storage Compliance Suite, UseCases, and PipelineFactory.
"""

import tempfile
from pathlib import Path

import pytest

from nexusai.kernel.outbox import JSONOutboxSerializer
from nexusai.memory.pipeline import PipelineFactory, RetrievalPipelineConfig
from nexusai.memory.storage import (
    FileMemoryStore,
    InMemoryMemoryStore,
    SQLiteMemoryStore,
    StorageComplianceSuite,
)


@pytest.mark.asyncio
async def test_in_memory_storage_compliance():
    store = InMemoryMemoryStore()
    await StorageComplianceSuite.verify_storage_compliance(store)


@pytest.mark.asyncio
async def test_file_storage_compliance():
    with tempfile.TemporaryDirectory() as tmp_dir:
        store = FileMemoryStore(tmp_dir)
        await StorageComplianceSuite.verify_storage_compliance(store)


@pytest.mark.asyncio
async def test_sqlite_storage_compliance():
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_memory.db"
        store = SQLiteMemoryStore(db_path)
        await StorageComplianceSuite.verify_storage_compliance(store)


def test_pipeline_factory_profiles():
    factory = PipelineFactory()
    factory.register_profile(
        profile_name="brain_profile",
        stages=[],
        config=RetrievalPipelineConfig(max_candidates=10),
    )

    pipeline = factory.create_pipeline("brain_profile")
    assert pipeline.config.max_candidates == 10


def test_versioned_json_outbox_serializer():
    serializer = JSONOutboxSerializer(schema_version="2.0.0")
    payload = serializer.serialize({"key": "value"}, event_type="MemoryStoredEvent")

    deserialized = serializer.deserialize(payload)
    assert deserialized["schema_version"] == "2.0.0"
    assert deserialized["event_type"] == "MemoryStoredEvent"
    assert deserialized["payload"]["key"] == "value"
