"""
Behavioral StorageComplianceSuite verifying MemoryStorage engines against behavioral contracts.
"""

from __future__ import annotations

from nexusai.memory.contracts.storage import MemoryStorage
from nexusai.memory.domain.content import MemoryContent
from nexusai.memory.domain.metadata import MemoryMetadata
from nexusai.memory.domain.record import MemoryRecord, MemoryScope, MemoryType


class StorageComplianceSuite:
    """Reusable behavioral compliance test suite verifying MemoryStorage engines."""

    @staticmethod
    async def verify_storage_compliance(storage: MemoryStorage) -> None:
        """Run comprehensive behavioral compliance assertions on target storage engine."""
        # 1. Save and Get Record
        content = MemoryContent(raw_text="Compliance test content: Bahasa Indonesia & Unicode: 🚀, Ñ, ü")
        metadata = MemoryMetadata(owner="test_user", tags=["test", "behavioral"])
        record = MemoryRecord(
            id="comp_rec_1",
            memory_type=MemoryType.SEMANTIC,
            scope=MemoryScope.USER,
            metadata=metadata,
            content=content,
        )

        await storage.save(record)

        fetched = await storage.get("comp_rec_1")
        assert fetched is not None, "Failed to retrieve saved record by ID"
        assert fetched.id == "comp_rec_1"
        assert fetched.content.raw_text == "Compliance test content: Bahasa Indonesia & Unicode: 🚀, Ñ, ü"
        assert fetched.metadata.owner == "test_user"
        assert fetched.metadata.created_at == record.metadata.created_at

        # 2. Overwrite Record with Same ID
        record.update_summary("Updated summary text")
        record.attach_embedding("emb_vec_999")
        await storage.save(record)

        overwritten = await storage.get("comp_rec_1")
        assert overwritten is not None
        assert overwritten.content.summary == "Updated summary text"
        assert overwritten.content.embedding_id == "emb_vec_999"

        # 3. Large Payload Test (> 1MB)
        large_text = "NexusAI Memory Storage Test Text Payload " * 25000  # ~1MB
        large_record = MemoryRecord(
            id="large_payload_rec",
            content=MemoryContent(raw_text=large_text),
        )
        await storage.save(large_record)

        fetched_large = await storage.get("large_payload_rec")
        assert fetched_large is not None
        assert len(fetched_large.content.raw_text) == len(large_text)

        # 4. List Records
        listed = await storage.list_records(limit=10)
        assert len(listed) >= 2, "Failed to list stored records"

        # 5. Delete Non-Existent Record (Should return False safely)
        non_existent_delete = await storage.delete("non_existent_id_999")
        assert non_existent_delete is False, "Deleting non-existent record should return False"

        # 6. Delete Existing Record
        deleted = await storage.delete("comp_rec_1")
        assert deleted is True, "Failed to delete existing record"

        post_delete = await storage.get("comp_rec_1")
        assert post_delete is None, "Record still exists after deletion"

        # Cleanup large record
        await storage.delete("large_payload_rec")
