"""
Unit tests for Milestone 3.1.6 Kernel Outbox Transactional Persistence.
"""

from __future__ import annotations

import json
from uuid import uuid4

import pytest

from nexusai.brain.domain import Message, MessageRole, SchemaVersion, Turn
from nexusai.brain.persistence import (
    InMemoryOutboxWriter,
    OutboxRecord,
    TurnPersistenceService,
)
from nexusai.brain.runtime import ExecutionContext, TurnMetrics


def test_outbox_record_json_serialization_boundary() -> None:
    """Verify OutboxRecord JSON contract boundary and serialization."""
    event_id = uuid4()
    exec_id = uuid4()

    record = OutboxRecord.create(
        event_type="BrainTurnCompletedEvent",
        execution_id=exec_id,
        payload={"user": "alice", "tokens": 120},
        event_id=event_id,
    )

    assert record.event_id == event_id
    assert record.execution_id == exec_id
    assert record.schema_version == SchemaVersion(1, 0)
    assert isinstance(record.payload_json, str)

    # Verify JSON string parses cleanly without pickle
    parsed_payload = json.loads(record.payload_json)
    assert parsed_payload["user"] == "alice"
    assert parsed_payload["tokens"] == 120

    d = record.to_dict()
    restored = OutboxRecord.from_dict(d)
    assert restored.event_id == event_id
    assert restored.execution_id == exec_id


@pytest.mark.asyncio
async def test_turn_persistence_service_write_behind() -> None:
    """Verify TurnPersistenceService schedules write-behind outbox records without blocking."""
    outbox_writer = InMemoryOutboxWriter()
    persistence_service = TurnPersistenceService(outbox_writer=outbox_writer)

    ctx = ExecutionContext()
    turn = Turn(
        user_message=Message(role=MessageRole.USER, content="Hello Outbox"),
        assistant_message=Message(role=MessageRole.ASSISTANT, content="Hi from Outbox"),
        status="COMPLETED",
    )
    metrics = TurnMetrics(ttft_ms=25.0, latency_ms=100.0, output_tokens=10)

    record = await persistence_service.schedule_turn_persistence(ctx, turn, metrics)

    assert isinstance(record, OutboxRecord)
    assert len(outbox_writer.records) == 1
    assert outbox_writer.records[0].event_type == "BrainTurnCompletedEvent"

    parsed_payload = json.loads(outbox_writer.records[0].payload_json)
    assert parsed_payload["user_message"] == "Hello Outbox"
    assert parsed_payload["status"] == "COMPLETED"
    assert parsed_payload["metrics"]["ttft_ms"] == 25.0
