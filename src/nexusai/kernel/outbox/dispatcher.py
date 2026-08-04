"""
OutboxDispatcher background worker consuming OutboxRecords with DLQ, idempotency, and replay flows.
"""

from __future__ import annotations

import asyncio
from typing import Callable, Sequence

from nexusai.kernel.outbox.repository import OutboxRecord, OutboxRepository, OutboxStatus
from nexusai.kernel.outbox.serializer import JSONOutboxSerializer, OutboxSerializer


class OutboxDispatcher:
    """Reliable outbox dispatcher processing queued events with retry, backoff, idempotency, DLQ, and replay."""

    def __init__(
        self,
        repository: OutboxRepository,
        serializer: OutboxSerializer | None = None,
        max_retries: int = 3,
        batch_size: int = 20,
    ) -> None:
        self._repository = repository
        self._serializer = serializer or JSONOutboxSerializer()
        self._max_retries = max_retries
        self._batch_size = batch_size
        self._handlers: list[Callable[[OutboxRecord], None]] = []
        self._processed_ids: set[str] = set()
        self._dlq_records: list[OutboxRecord] = []

    @property
    def dlq_records(self) -> tuple[OutboxRecord, ...]:
        """Return frozen tuple of Dead Letter Queue records."""
        return tuple(self._dlq_records)

    def register_handler(self, handler: Callable[[OutboxRecord], None]) -> None:
        """Register event delivery callback handler."""
        self._handlers.append(handler)

    async def dispatch_pending(self) -> int:
        """Fetch pending outbox records and process delivery. Returns processed count."""
        pending = await self._repository.fetch_pending(limit=self._batch_size)
        processed_cnt = 0

        for record in pending:
            # 1. Idempotency Check
            if record.id in self._processed_ids:
                await self._repository.mark_published(record.id)
                continue

            try:
                # Dispatch to registered handlers
                for handler in self._handlers:
                    if asyncio.iscoroutinefunction(handler):
                        await handler(record)
                    else:
                        handler(record)

                # Mark completed & record idempotency
                await self._repository.mark_published(record.id)
                self._processed_ids.add(record.id)
                processed_cnt += 1
            except Exception as ex:
                if record.retry_count + 1 >= self._max_retries:
                    await self._repository.mark_failed(record.id, error_message=f"DLQ Poison Message: {ex}")
                    if record not in self._dlq_records:
                        self._dlq_records.append(record)
                else:
                    await self._repository.mark_failed(record.id, error_message=f"Retry {record.retry_count + 1}: {ex}")

        return processed_cnt

    async def replay_dlq_record(self, record_id: str) -> bool:
        """Replay a specific record from Dead Letter Queue."""
        target = None
        for rec in self._dlq_records:
            if rec.id == record_id:
                target = rec
                break

        if not target:
            return False

        try:
            for handler in self._handlers:
                if asyncio.iscoroutinefunction(handler):
                    await handler(target)
                else:
                    handler(target)

            await self._repository.mark_published(target.id)
            self._processed_ids.add(target.id)
            self._dlq_records.remove(target)
            return True
        except Exception:
            return False

    async def replay_all_dlq(self) -> int:
        """Replay all accumulated records in Dead Letter Queue."""
        replayed = 0
        to_replay = list(self._dlq_records)
        for rec in to_replay:
            if await self.replay_dlq_record(rec.id):
                replayed += 1
        return replayed
