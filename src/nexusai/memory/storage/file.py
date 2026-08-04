"""
FileMemoryStore storage implementation consuming MemorySerializer dependency injection.
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from nexusai.memory.contracts.storage import MemoryStorage
from nexusai.memory.domain.record import MemoryRecord
from nexusai.memory.serializer import JSONMemorySerializer, MemorySerializer


class FileMemoryStore(MemoryStorage):
    """File-based persistence storage engine using MemorySerializer dependency injection."""

    def __init__(self, storage_dir: str | Path, serializer: MemorySerializer | None = None) -> None:
        self._dir = Path(storage_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._serializer = serializer or JSONMemorySerializer()

    def _file_path(self, record_id: str) -> Path:
        return self._dir / f"{record_id}.bin"

    async def save(self, record: MemoryRecord) -> None:
        """Save MemoryRecord to file using serializer."""
        file_path = self._file_path(record.id)
        payload_bytes = self._serializer.serialize(record)
        with open(file_path, "wb") as f:
            f.write(payload_bytes)

    async def get(self, record_id: str) -> MemoryRecord | None:
        """Get MemoryRecord from file using serializer."""
        file_path = self._file_path(record_id)
        if not file_path.exists():
            return None
        with open(file_path, "rb") as f:
            payload_bytes = f.read()
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
                with open(file_path, "rb") as f:
                    payload_bytes = f.read()
                records.append(self._serializer.deserialize(payload_bytes))
            except Exception:
                continue
        return records
