"""
FileMemoryStore storage implementation consuming MemorySerializer dependency injection.
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Sequence

from nexusai.logging.logger import logger
from nexusai.memory.contracts.storage import MemoryStorage
from nexusai.memory.domain.record import MemoryRecord
from nexusai.memory.serializer import JSONMemorySerializer, MemorySerializer


_SAFE_RECORD_ID = re.compile(r"^[A-Za-z0-9_.-]+$")


class FileMemoryStore(MemoryStorage):
    """File-based persistence storage engine using MemorySerializer dependency injection."""

    def __init__(self, storage_dir: str | Path, serializer: MemorySerializer | None = None) -> None:
        self._dir = Path(storage_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._serializer = serializer or JSONMemorySerializer()

    def _file_path(self, record_id: str) -> Path:
        # Record IDs become file names: reject separators and ".." so they cannot escape _dir.
        if not _SAFE_RECORD_ID.match(record_id) or record_id in (".", ".."):
            raise ValueError(f"Invalid memory record id: {record_id!r}")
        return self._dir / f"{record_id}.bin"

    async def save(self, record: MemoryRecord) -> None:
        """Save MemoryRecord to file using serializer."""
        file_path = self._file_path(record.id)
        payload_bytes = self._serializer.serialize(record)
        await asyncio.to_thread(file_path.write_bytes, payload_bytes)

    async def get(self, record_id: str) -> MemoryRecord | None:
        """Get MemoryRecord from file using serializer."""
        file_path = self._file_path(record_id)
        if not file_path.exists():
            return None
        payload_bytes = await asyncio.to_thread(file_path.read_bytes)
        return self._serializer.deserialize(payload_bytes)

    async def delete(self, record_id: str) -> bool:
        """Delete file for MemoryRecord."""
        file_path = self._file_path(record_id)
        if file_path.exists():
            file_path.unlink()
            return True
        return False

    async def list_records(self, limit: int = 100) -> Sequence[MemoryRecord]:
        """List stored MemoryRecords up to limit."""
        records: list[MemoryRecord] = []
        for file_path in list(self._dir.glob("*.bin"))[:limit]:
            try:
                payload_bytes = await asyncio.to_thread(file_path.read_bytes)
                records.append(self._serializer.deserialize(payload_bytes))
            except Exception as exc:
                logger.warning(
                    "FileMemoryStore: skipping unreadable record {}: {!r}", file_path, exc
                )
                continue
        return records
