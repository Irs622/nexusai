"""
KernelOutboxAdapter and InMemoryOutboxWriter implementing IOutboxWriter port.
"""

from __future__ import annotations

from typing import Any

from nexusai.brain.persistence.contracts import IOutboxWriter, OutboxRecord
from nexusai.logging.logger import logger


class InMemoryOutboxWriter(IOutboxWriter):
    """In-memory outbox writer for testing and local execution without Kernel Outbox."""

    def __init__(self) -> None:
        self.records: list[OutboxRecord] = []

    async def write_record(self, record: OutboxRecord) -> bool:
        """Write OutboxRecord to in-memory transaction buffer."""
        self.records.append(record)
        logger.debug(
            f"InMemoryOutboxWriter recorded event '{record.event_type}' (id={record.event_id})"
        )
        return True


class KernelOutboxAdapter(IOutboxWriter):
    """Adapter bridging Brain Runtime outbox writes to Kernel Transactional Outbox engine."""

    def __init__(self, kernel_outbox_manager: Any | None = None) -> None:
        """Initialize KernelOutboxAdapter with optional Kernel Outbox Manager reference.

        Args:
            kernel_outbox_manager: Reference to Kernel's outbox persistence service.
        """
        self._kernel_outbox = kernel_outbox_manager
        self._fallback_writer = InMemoryOutboxWriter()

    async def write_record(self, record: OutboxRecord) -> bool:
        """Write OutboxRecord using Kernel Outbox Manager or fallback writer.

        Args:
            record: OutboxRecord to persist.

        Returns:
            True if write succeeded.
        """
        if self._kernel_outbox is not None and hasattr(self._kernel_outbox, "enqueue"):
            try:
                await self._kernel_outbox.enqueue(
                    event_id=str(record.event_id),
                    execution_id=str(record.execution_id),
                    event_type=record.event_type,
                    payload=record.payload_json,
                )
                logger.info(f"Enqueued record to Kernel Outbox: {record.event_type}")
                return True
            except Exception as e:
                logger.error(f"Failed to write to Kernel Outbox: {e}")
                # Fallback write
                return await self._fallback_writer.write_record(record)
        else:
            return await self._fallback_writer.write_record(record)
