"""Qdrant VectorStore adapter conforming to VectorStore contract."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any

from nexusai.logging.logger import logger
from nexusai.memory.contracts.vector import (
    DistanceMetric,
    VectorCapabilities,
    VectorMatch,
    VectorRecord,
    VectorStore,
)
from nexusai.memory.vector.in_memory import InMemoryVectorStore


def _get_qdrant_models() -> Any:
    """Retrieve qdrant_client.http.models or lightweight duck-typing stubs if not installed."""
    try:
        from qdrant_client.http import models as rest_models

        return rest_models
    except ImportError:

        class _MockFieldCondition:
            def __init__(self, key: str, match: Any) -> None:
                self.key = key
                self.match = match

        class _MockMatchValue:
            def __init__(self, value: Any) -> None:
                self.value = value

        class _MockFilter:
            def __init__(self, must: list[Any] | None = None) -> None:
                self.must = must or []

        class _MockFilterSelector:
            def __init__(self, filter: Any) -> None:
                self.filter = filter

        class _MockPointStruct:
            def __init__(self, id: str, vector: list[float], payload: dict[str, Any]) -> None:
                self.id = id
                self.vector = vector
                self.payload = payload

        class _MockDistance:
            COSINE = "Cosine"
            EUCLID = "Euclid"
            DOT = "Dot"

        class _MockVectorParams:
            def __init__(self, size: int, distance: Any) -> None:
                self.size = size
                self.distance = distance

        class _MockHnswConfigDiff:
            def __init__(self, m: int = 16, ef_construct: int = 64) -> None:
                self.m = m
                self.ef_construct = ef_construct

        class _ModelsModule:
            FieldCondition = _MockFieldCondition
            MatchValue = _MockMatchValue
            Filter = _MockFilter
            FilterSelector = _MockFilterSelector
            PointStruct = _MockPointStruct
            Distance = _MockDistance
            VectorParams = _MockVectorParams
            HnswConfigDiff = _MockHnswConfigDiff

        return _ModelsModule()


class QdrantVectorStore(VectorStore):
    """Qdrant vector store backend using asynchronous Qdrant client."""

    def __init__(
        self,
        url: str | None = None,
        api_key: str | None = None,
        collection_name: str = "nexusai_vectors",
        dimensions: int = 768,
        client: Any | None = None,
        fallback_enabled: bool = True,
    ) -> None:
        self._url = url
        self._api_key = api_key
        self._collection_name = collection_name
        self._dimensions = dimensions
        self._client = client
        self._fallback_enabled = fallback_enabled
        self._initialized = False

        self._capabilities = VectorCapabilities(
            provider_name="qdrant_vector_store",
            dimensions=dimensions,
            supported_metrics=(
                DistanceMetric.COSINE,
                DistanceMetric.EUCLIDEAN,
                DistanceMetric.DOT_PRODUCT,
            ),
            supports_namespaces=True,
            supports_metadata_filtering=True,
            supports_batch=True,
        )

        # In-memory fallback engine if qdrant_client is not installed or unconfigured
        self._fallback = InMemoryVectorStore(provider_name="qdrant_fallback", dimensions=dimensions)
        self._use_fallback = False

    @property
    def capabilities(self) -> VectorCapabilities:
        """Return Qdrant capabilities descriptor."""
        return self._capabilities

    @property
    def collection_name(self) -> str:
        """Return collection name."""
        return self._collection_name

    @property
    def is_fallback(self) -> bool:
        """Return True if currently running in fallback mode."""
        return self._use_fallback

    def _to_uuid(self, record_id: str, namespace: str) -> str:
        """Deterministically map arbitrary string record ID and namespace into standard RFC 4122 UUID."""
        return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{namespace}:{record_id}"))

    async def _get_client(self) -> Any:
        """Retrieve or lazily initialize AsyncQdrantClient."""
        if self._use_fallback:
            return None

        if self._client is not None:
            if not self._initialized:
                await self._init_collection(self._client)
            return self._client

        if not self._url:
            if self._fallback_enabled:
                self._use_fallback = True
                logger.debug(
                    "[QdrantVectorStore] No Qdrant URL configured. Operating in in-memory fallback mode."
                )
                return None
            raise ValueError("Qdrant URL must be provided when fallback is disabled.")

        try:
            from qdrant_client import AsyncQdrantClient

            self._client = AsyncQdrantClient(
                url=self._url,
                api_key=self._api_key,
                timeout=30.0,
            )
            await self._init_collection(self._client)
            return self._client
        except ImportError:
            if self._fallback_enabled:
                self._use_fallback = True
                logger.warning(
                    "[QdrantVectorStore] 'qdrant-client' library not installed. Falling back to InMemoryVectorStore. "
                    "Install with: pip install nexusai[qdrant]"
                )
                return None
            raise RuntimeError(
                "The 'qdrant-client' library is required for QdrantVectorStore. Install via: pip install nexusai[qdrant]"
            )
        except Exception as e:
            if self._fallback_enabled:
                self._use_fallback = True
                logger.warning(
                    f"[QdrantVectorStore] Failed to initialize Qdrant ({e}). Operating in in-memory fallback mode."
                )
                return None
            raise

    async def _init_collection(self, client: Any) -> None:
        """Verify existence of target collection or create it with Cosine HNSW config."""
        if self._initialized:
            return

        try:
            # Check if collection exists
            collections_res = await client.get_collections()
            collection_names = [c.name for c in collections_res.collections]

            if self._collection_name not in collection_names:
                rest_models = _get_qdrant_models()

                await client.create_collection(
                    collection_name=self._collection_name,
                    vectors_config=rest_models.VectorParams(
                        size=self._dimensions,
                        distance=rest_models.Distance.COSINE,
                    ),
                    hnsw_config=rest_models.HnswConfigDiff(
                        m=16,
                        ef_construct=64,
                    ),
                )
                logger.debug(
                    f"[QdrantVectorStore] Created collection '{self._collection_name}' ({self._dimensions} dims)"
                )
        except Exception as coll_err:
            logger.debug(f"[QdrantVectorStore] Collection check/create note: {coll_err}")

        self._initialized = True

    async def upsert(self, record: VectorRecord) -> None:
        """Upsert a single VectorRecord into Qdrant."""
        await self.batch_upsert([record])

    async def batch_upsert(self, records: Sequence[VectorRecord]) -> None:
        """Batch upsert multiple VectorRecords."""
        client = await self._get_client()
        if client is None:
            await self._fallback.batch_upsert(records)
            return

        if not records:
            return

        rest_models = _get_qdrant_models()

        points: list[Any] = []
        for r in records:
            point_id = self._to_uuid(r.record_id, r.namespace)
            payload = {
                "_nexus_record_id": r.record_id,
                "_nexus_namespace": r.namespace,
                "_nexus_payload": r.payload,
                **(r.metadata or {}),
            }
            points.append(
                rest_models.PointStruct(
                    id=point_id,
                    vector=list(r.vector),
                    payload=payload,
                )
            )

        await client.upsert(
            collection_name=self._collection_name,
            points=points,
            wait=True,
        )

    async def get(self, record_id: str, namespace: str = "default") -> VectorRecord | None:
        """Retrieve a single VectorRecord by ID."""
        client = await self._get_client()
        if client is None:
            return await self._fallback.get(record_id, namespace=namespace)

        point_id = self._to_uuid(record_id, namespace)
        try:
            points = await client.retrieve(
                collection_name=self._collection_name,
                ids=[point_id],
                with_payload=True,
                with_vectors=True,
            )
        except Exception:
            return None

        if not points:
            return None

        p = points[0]
        payload = p.payload or {}
        # Ensure point belongs to requested namespace
        if payload.get("_nexus_namespace") != namespace:
            return None

        raw_vec = p.vector
        vector = list(raw_vec) if isinstance(raw_vec, (list, tuple)) else []
        metadata = {k: v for k, v in payload.items() if not k.startswith("_nexus_")}

        return VectorRecord(
            record_id=payload.get("_nexus_record_id", record_id),
            vector=vector,
            metadata=metadata,
            namespace=namespace,
            payload=payload.get("_nexus_payload"),
        )

    async def delete(self, record_id: str, namespace: str = "default") -> bool:
        """Delete a single vector record by ID."""
        deleted_count = await self.batch_delete([record_id], namespace=namespace)
        return deleted_count > 0

    async def batch_delete(self, record_ids: Sequence[str], namespace: str = "default") -> int:
        """Delete a batch of vector records by ID."""
        client = await self._get_client()
        if client is None:
            return await self._fallback.batch_delete(record_ids, namespace=namespace)

        if not record_ids:
            return 0

        # Verify how many exist before deleting to return accurate count
        point_ids = [self._to_uuid(rid, namespace) for rid in record_ids]
        try:
            existing = await client.retrieve(
                collection_name=self._collection_name,
                ids=point_ids,
            )
            count = len(existing)
            if count > 0:
                await client.delete(
                    collection_name=self._collection_name,
                    points_selector=point_ids,
                    wait=True,
                )
            return count
        except Exception:
            return 0

    async def search(
        self,
        query_vector: Sequence[float],
        top_k: int = 5,
        namespace: str = "default",
        filter_dict: dict[str, Any] | None = None,
    ) -> Sequence[VectorMatch]:
        """Perform nearest-neighbor vector search in Qdrant."""
        client = await self._get_client()
        if client is None:
            return await self._fallback.search(
                query_vector, top_k=top_k, namespace=namespace, filter_dict=filter_dict
            )

        rest_models = _get_qdrant_models()

        must_conditions: list[Any] = [
            rest_models.FieldCondition(
                key="_nexus_namespace",
                match=rest_models.MatchValue(value=namespace),
            )
        ]

        if filter_dict:
            for k, v in filter_dict.items():
                must_conditions.append(
                    rest_models.FieldCondition(
                        key=k,
                        match=rest_models.MatchValue(value=v),
                    )
                )

        query_filter = rest_models.Filter(must=must_conditions)

        results = await client.search(
            collection_name=self._collection_name,
            query_vector=list(query_vector),
            limit=top_k,
            query_filter=query_filter,
            with_payload=True,
        )

        matches: list[VectorMatch] = []
        for scored_point in results:
            payload = scored_point.payload or {}
            metadata = {k: v for k, v in payload.items() if not k.startswith("_nexus_")}
            sim = float(scored_point.score)
            dist = max(0.0, 1.0 - sim)

            matches.append(
                VectorMatch(
                    record_id=payload.get("_nexus_record_id", str(scored_point.id)),
                    distance=dist,
                    similarity=sim,
                    metadata=metadata,
                    payload=payload.get("_nexus_payload"),
                    namespace=namespace,
                    provider_metadata={
                        "backend": "qdrant",
                        "collection": self._collection_name,
                    },
                )
            )

        return matches

    async def count(self, namespace: str = "default") -> int:
        """Count total vector records within namespace."""
        client = await self._get_client()
        if client is None:
            return await self._fallback.count(namespace=namespace)

        rest_models = _get_qdrant_models()

        count_filter = rest_models.Filter(
            must=[
                rest_models.FieldCondition(
                    key="_nexus_namespace",
                    match=rest_models.MatchValue(value=namespace),
                )
            ]
        )
        res = await client.count(
            collection_name=self._collection_name,
            count_filter=count_filter,
            exact=True,
        )
        return int(res.count)

    async def clear(self, namespace: str = "default") -> None:
        """Clear all vector records within namespace."""
        client = await self._get_client()
        if client is None:
            await self._fallback.clear(namespace=namespace)
            return

        rest_models = _get_qdrant_models()

        filter_selector = rest_models.FilterSelector(
            filter=rest_models.Filter(
                must=[
                    rest_models.FieldCondition(
                        key="_nexus_namespace",
                        match=rest_models.MatchValue(value=namespace),
                    )
                ]
            )
        )
        await client.delete(
            collection_name=self._collection_name,
            points_selector=filter_selector,
            wait=True,
        )

    async def health(self) -> dict[str, Any]:
        """Return health status dictionary."""
        await self._get_client()
        return {
            "provider": self.capabilities.provider_name,
            "dimensions": self.capabilities.dimensions,
            "collection": self._collection_name,
            "healthy": True,
            "is_fallback": self._use_fallback,
        }

    async def close(self) -> None:
        """Close Qdrant client."""
        if self._client is not None and not self._use_fallback:
            try:
                await self._client.close()
            except Exception as e:
                logger.debug(f"[QdrantVectorStore] Error closing client: {e}")
            self._client = None
