"""
VectorComplianceSuite for compliance verification of VectorStore backends.
"""

from __future__ import annotations

from nexusai.memory.contracts.vector import VectorRecord, VectorStore


class VectorComplianceSuite:
    """Reusable behavioral compliance test suite verifying any VectorStore engine."""

    @staticmethod
    async def verify_vector_store_compliance(store: VectorStore) -> None:
        """Run comprehensive behavioral compliance assertions on target VectorStore engine."""
        caps = store.capabilities
        dim = caps.dimensions

        # 1. Search Empty Database
        empty_search = await store.search(query_vector=[0.1] * dim, top_k=5, namespace="default")
        assert len(empty_search) == 0, "Search on empty database must return empty list"

        # 2. Upsert and Get Single Vector
        v1 = VectorRecord(
            record_id="v_1",
            vector=[0.5] * dim,
            metadata={"category": "ai", "tag": "agent"},
            namespace="default",
            payload="Sample vector 1 payload",
        )
        await store.upsert(v1)

        fetched_v1 = await store.get("v_1", namespace="default")
        assert fetched_v1 is not None, "Failed to get vector by ID"
        assert fetched_v1.record_id == "v_1"
        assert fetched_v1.metadata["category"] == "ai"

        # 3. Overwrite Vector
        v1_updated = VectorRecord(
            record_id="v_1",
            vector=[0.9] * dim,
            metadata={"category": "ai", "tag": "updated"},
            namespace="default",
            payload="Updated payload",
        )
        await store.upsert(v1_updated)

        fetched_v1_up = await store.get("v_1", namespace="default")
        assert fetched_v1_up is not None
        assert fetched_v1_up.metadata["tag"] == "updated"

        # 4. Batch Upsert
        v2 = VectorRecord(record_id="v_2", vector=[0.2] * dim, metadata={"category": "tools"}, namespace="default")
        v3 = VectorRecord(record_id="v_3", vector=[0.8] * dim, metadata={"category": "ai"}, namespace="default")
        await store.batch_upsert([v2, v3])

        cnt = await store.count(namespace="default")
        assert cnt == 3, f"Expected count 3, got {cnt}"

        # 5. Metadata Filtered Search
        filtered_res = await store.search(
            query_vector=[0.8] * dim,
            top_k=5,
            namespace="default",
            filter_dict={"category": "ai"},
        )
        assert len(filtered_res) >= 1
        assert all(r.metadata.get("category") == "ai" for r in filtered_res)

        # 6. Namespace Isolation
        v_ns_brain = VectorRecord(record_id="v_brain_1", vector=[0.9] * dim, namespace="brain")
        await store.upsert(v_ns_brain)

        search_ns_brain = await store.search([0.9] * dim, top_k=5, namespace="brain")
        assert len(search_ns_brain) == 1
        assert search_ns_brain[0].record_id == "v_brain_1"

        search_ns_default = await store.search([0.9] * dim, top_k=5, namespace="default")
        assert not any(r.record_id == "v_brain_1" for r in search_ns_default), "Record leaked across namespaces"

        # 7. Delete Non-Existent
        del_non_existent = await store.delete("v_non_existent", namespace="default")
        assert del_non_existent is False

        # 8. Batch Delete
        deleted_cnt = await store.batch_delete(["v_1", "v_2"], namespace="default")
        assert deleted_cnt == 2

        # Cleanup
        await store.clear(namespace="default")
        await store.clear(namespace="brain")
