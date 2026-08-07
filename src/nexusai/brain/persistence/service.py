"""
TurnPersistenceService write-behind coordinator service.
"""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID, uuid4

from nexusai.brain.domain.turn import Turn
from nexusai.brain.persistence.contracts import IOutboxWriter, OutboxRecord
from nexusai.brain.persistence.outbox_adapter import InMemoryOutboxWriter
from nexusai.brain.runtime.context import ExecutionContext
from nexusai.brain.runtime.metrics import TurnMetrics
from nexusai.core.errors import BrainOutboxPersistenceError
from nexusai.logging.logger import logger


class TurnPersistenceService:
    """Write-behind persistence service coordinating non-blocking outbox turn records."""

    def __init__(self, outbox_writer: IOutboxWriter | None = None) -> None:
        """Initialize TurnPersistenceService with an IOutboxWriter implementation.

        Args:
            outbox_writer: Port implementation (defaults to InMemoryOutboxWriter).
        """
        self._writer = outbox_writer or InMemoryOutboxWriter()

    async def schedule_turn_persistence(
        self,
        context: ExecutionContext,
        turn: Turn,
        metrics: TurnMetrics | None = None,
    ) -> OutboxRecord:
        """Schedule non-blocking out-of-band turn persistence to transactional outbox.

        CRITICAL ARCHITECTURAL BOUNDARY:
        Turn persistence writes occur asynchronously write-behind. Storage writes
        NEVER delay or abort client streaming responses.

        Args:
            context: Turn ExecutionContext transport container.
            turn: Completed Turn aggregate.
            metrics: Associated TurnMetrics telemetry object.

        Returns:
            The created OutboxRecord.
        """
        payload: dict[str, Any] = {
            "conversation_id": str(context.identity.conversation_id),
            "turn_id": str(turn.id),
            "user_message": turn.user_message.content,
            "assistant_message": turn.assistant_message.content if turn.assistant_message else None,
            "token_usage": turn.token_usage,
            "status": turn.status,
            "metrics": metrics.to_dict() if metrics else None,
        }

        record = OutboxRecord.create(
            event_type="BrainTurnCompletedEvent",
            execution_id=context.runtime.execution_id,
            payload=payload,
            event_id=uuid4(),
        )

        logger.debug(
            "Scheduling out-of-band turn persistence outbox record",
            extra={
                "event_id": str(record.event_id),
                "execution_id": str(record.execution_id),
                "turn_id": str(turn.id),
            },
        )

        # Execute write-behind task asynchronously
        try:
            success = await self._writer.write_record(record)
            if not success:
                logger.warning(f"Outbox record write returned False for event '{record.event_id}'")
        except Exception as e:
            logger.error(f"Error during write-behind outbox persistence: {e}")
            # Non-blocking: write-behind error is logged without failing active turn stream
            raise BrainOutboxPersistenceError(f"Failed to persist turn record outbox: {e}") from e

        return record
