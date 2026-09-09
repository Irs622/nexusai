"""PostgreSQL pgvector VectorStore adapter conforming to VectorStore contract."""

from __future__ import annotations

import importlib
import json
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


class PgVectorStore(VectorStore):
    """PostgreSQL pgvector vector store backend using asyncpg with connection pooling."""

    def __init__(
        self,
        dsn: str | None = None,
        table_name: str = "nexusai_vectors",
        dimensions: int = 768,
        index_type: str = "hnsw",
        distance_metric: DistanceMetric = DistanceMetric.COSINE,
        pool: Any | None = None,
        fallback_enabled: bool = True,
    ) -> None:
        self._dsn = dsn
        self._table_name = table_name.replace("-", "_").replace(" ", "_")
        self._dimensions = dimensions
        self._index_type = index_type.lower()
        self._distance_metric = distance_metric
        self._pool = pool
        self._fallback_enabled = fallback_enabled
        self._initialized = False

        self._capabilities = VectorCapabilities(
            provider_name="pgvector_store",
            dimensions=dimensions,
            supported_metrics=(
                DistanceMetric.COSINE,
                DistanceMetric.EUCLIDEAN,
                DistanceMetric.INNER_PRODUCT,
            ),
            supports_namespaces=True,
            supports_metadata_filtering=True,
            supports_batch=True,
        )

        # In-memory fallback engine if asyncpg/postgres is unavailable
        self._fallback = InMemoryVectorStore(
            provider_name="pgvector_fallback", dimensions=dimensions
        )
        self._use_fallback = False

    @property
    def capabilities(self) -> VectorCapabilities:
        """Return pgvector capabilities descriptor."""
        return self._capabilities

    @property
    def table_name(self) -> str:
        """Return configured table name."""
        return self._table_name

    @property
    def is_fallback(self) -> bool:
        """Return True if currently operating in fallback mode."""
        return self._use_fallback

    async def _get_pool(self) -> Any:
        """Retrieve or lazily initialize asyncpg connection pool."""
        if self._use_fallback:
            return None

        if self._pool is not None:
            if not self._initialized:
                await self._init_schema(self._pool)
            return self._pool

        if not self._dsn:
            if self._fallback_enabled:
                self._use_fallback = True
                logger.debug(
                    "[PgVectorStore] No PostgreSQL DSN configured. Operating in in-memory fallback mode."
                )
                return None
            raise ValueError("PostgreSQL DSN must be provided when fallback is disabled.")

        try:
            asyncpg_mod: Any = importlib.import_module("asyncpg")

            self._pool = await asyncpg_mod.create_pool(
                dsn=self._dsn,
                min_size=1,
                max_size=10,
                command_timeout=30.0,
            )
            await self._init_schema(self._pool)
            return self._pool
        except (ImportError, ModuleNotFoundError):
            if self._fallback_enabled:
                self._use_fallback = True
                logger.warning(
                    "[PgVectorStore] 'asyncpg' library not installed. Falling back to InMemoryVectorStore. "
                    "Install with: pip install nexusai[postgres]"
                )
                return None
            raise RuntimeError(
                "The 'asyncpg' library is required for PgVectorStore. Install via: pip install nexusai[postgres]"
            )
        except Exception as e:
            if self._fallback_enabled:
                self._use_fallback = True
                logger.warning(
                    f"[PgVectorStore] Failed to connect to PostgreSQL ({e}). Operating in in-memory fallback mode."
                )
                return None
            raise

    async def _init_schema(self, pool: Any) -> None:
        """Initialize pgvector extension, table schema, and index."""
        if self._initialized:
            return

        async with pool.acquire() as conn:
            # 1. Enable extension
            await conn.execute("CREATE EXTENSION IF NOT EXISTS vector;")

            # 2. Create target table
            create_table_sql = f"""
            CREATE TABLE IF NOT EXISTS {self._table_name} (
                record_id VARCHAR(255) PRIMARY KEY,
                namespace VARCHAR(255) NOT NULL DEFAULT 'default',
                vector vector({self._dimensions}) NOT NULL,
                metadata JSONB DEFAULT '{{}}'::jsonb,
                payload TEXT,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW()
            );
            CREATE INDEX IF NOT EXISTS {self._table_name}_ns_idx ON {self._table_name} (namespace);
            """
            await conn.execute(create_table_sql)

            # 3. Create Vector Index (HNSW or IVFFlat)
            index_name = f"{self._table_name}_{self._index_type}_idx"
            if self._index_type == "ivfflat":
                idx_sql = f"""
                CREATE INDEX IF NOT EXISTS {index_name}
                ON {self._table_name} USING ivfflat (vector vector_cosine_ops)
                WITH (lists = 100);
                """
            else:  # Default to HNSW
                idx_sql = f"""
                CREATE INDEX IF NOT EXISTS {index_name}
                ON {self._table_name} USING hnsw (vector vector_cosine_ops)
                WITH (m = 16, ef_construction = 64);
                """
            try:
                await conn.execute(idx_sql)
            except Exception as idx_err:
                logger.debug(f"[PgVectorStore] Note on vector index creation: {idx_err}")

        self._initialized = True

    def _vector_to_str(self, vec: Sequence[float]) -> str:
        """Format Python float sequence into pgvector literal format: '[1.0, 2.0, ...]'."""
        return "[" + ", ".join(f"{x:.8f}" for x in vec) + "]"

    def _str_to_vector(self, vec_str: str) -> list[float]:
        """Parse pgvector literal '[0.1, 0.2]' into Python float list."""
        cleaned = vec_str.strip("[] \t\r\n")
        if not cleaned:
            return []
        return [float(x.strip()) for x in cleaned.split(",")]

    async def upsert(self, record: VectorRecord) -> None:
        """Upsert a single VectorRecord into PostgreSQL."""
        pool = await self._get_pool()
        if pool is None:
            await self._fallback.upsert(record)
            return

        sql = f"""
        INSERT INTO {self._table_name} (record_id, namespace, vector, metadata, payload, updated_at)
        VALUES ($1, $2, $3::vector, $4::jsonb, $5, NOW())
        ON CONFLICT (record_id) DO UPDATE SET
            namespace = EXCLUDED.namespace,
            vector = EXCLUDED.vector,
            metadata = EXCLUDED.metadata,
            payload = EXCLUDED.payload,
            updated_at = NOW();
        """
        vec_str = self._vector_to_str(record.vector)
        meta_json = json.dumps(record.metadata or {})

        async with pool.acquire() as conn:
            await conn.execute(
                sql, record.record_id, record.namespace, vec_str, meta_json, record.payload
            )

    async def batch_upsert(self, records: Sequence[VectorRecord]) -> None:
        """Batch upsert multiple VectorRecords."""
        pool = await self._get_pool()
        if pool is None:
            await self._fallback.batch_upsert(records)
            return

        if not records:
            return

        sql = f"""
        INSERT INTO {self._table_name} (record_id, namespace, vector, metadata, payload, updated_at)
        VALUES ($1, $2, $3::vector, $4::jsonb, $5, NOW())
        ON CONFLICT (record_id) DO UPDATE SET
            namespace = EXCLUDED.namespace,
            vector = EXCLUDED.vector,
            metadata = EXCLUDED.metadata,
            payload = EXCLUDED.payload,
            updated_at = NOW();
        """
        data = [
            (
                r.record_id,
                r.namespace,
                self._vector_to_str(r.vector),
                json.dumps(r.metadata or {}),
                r.payload,
            )
            for r in records
        ]
        async with pool.acquire() as conn:
            await conn.executemany(sql, data)

    async def delete(self, record_id: str, namespace: str = "default") -> bool:
        """Delete a single vector record by ID within target namespace."""
        pool = await self._get_pool()
        if pool is None:
            return await self._fallback.delete(record_id, namespace=namespace)

        sql = f"DELETE FROM {self._table_name} WHERE record_id = $1 AND namespace = $2;"
        async with pool.acquire() as conn:
            res = await conn.execute(sql, record_id, namespace)
            # res format: 'DELETE N'
            parts = res.split()
            return len(parts) > 1 and int(parts[-1]) > 0

    async def batch_delete(self, record_ids: Sequence[str], namespace: str = "default") -> int:
        """Delete a batch of vector records by ID."""
        pool = await self._get_pool()
        if pool is None:
            return await self._fallback.batch_delete(record_ids, namespace=namespace)

        if not record_ids:
            return 0

        sql = f"DELETE FROM {self._table_name} WHERE namespace = $1 AND record_id = ANY($2::varchar[]);"
        async with pool.acquire() as conn:
            res = await conn.execute(sql, namespace, list(record_ids))
            parts = res.split()
            return int(parts[-1]) if len(parts) > 1 else 0

    async def get(self, record_id: str, namespace: str = "default") -> VectorRecord | None:
        """Get a single vector record by ID."""
        pool = await self._get_pool()
        if pool is None:
            return await self._fallback.get(record_id, namespace=namespace)

        sql = f"""
        SELECT record_id, namespace, vector::text, metadata, payload
        FROM {self._table_name}
        WHERE record_id = $1 AND namespace = $2;
        """
        async with pool.acquire() as conn:
            row = await conn.fetchrow(sql, record_id, namespace)
            if not row:
                return None

            raw_meta = row["metadata"]
            metadata: dict[str, Any] = (
                json.loads(raw_meta) if isinstance(raw_meta, str) else dict(raw_meta or {})
            )
            return VectorRecord(
                record_id=row["record_id"],
                vector=self._str_to_vector(row["vector"]),
                metadata=metadata,
                namespace=row["namespace"],
                payload=row["payload"],
            )

    async def search(
        self,
        query_vector: Sequence[float],
        top_k: int = 5,
        namespace: str = "default",
        filter_dict: dict[str, Any] | None = None,
    ) -> Sequence[VectorMatch]:
        """Perform cosine similarity nearest-neighbor search using pgvector '<=>' operator."""
        pool = await self._get_pool()
        if pool is None:
            return await self._fallback.search(
                query_vector, top_k=top_k, namespace=namespace, filter_dict=filter_dict
            )

        vec_str = self._vector_to_str(query_vector)

        if filter_dict:
            filter_json = json.dumps(filter_dict)
            sql = f"""
            SELECT record_id, namespace, metadata, payload,
                   (vector <=> $1::vector) AS distance,
                   (1.0 - (vector <=> $1::vector)) AS similarity
            FROM {self._table_name}
            WHERE namespace = $2 AND metadata @> $4::jsonb
            ORDER BY vector <=> $1::vector ASC
            LIMIT $3;
            """
            params = [vec_str, namespace, top_k, filter_json]
        else:
            sql = f"""
            SELECT record_id, namespace, metadata, payload,
                   (vector <=> $1::vector) AS distance,
                   (1.0 - (vector <=> $1::vector)) AS similarity
            FROM {self._table_name}
            WHERE namespace = $2
            ORDER BY vector <=> $1::vector ASC
            LIMIT $3;
            """
            params = [vec_str, namespace, top_k]

        matches: list[VectorMatch] = []
        async with pool.acquire() as conn:
            rows = await conn.fetch(sql, *params)
            for row in rows:
                raw_meta = row["metadata"]
                metadata: dict[str, Any] = (
                    json.loads(raw_meta) if isinstance(raw_meta, str) else dict(raw_meta or {})
                )
                dist = float(row["distance"])
                sim = float(row["similarity"])
                matches.append(
                    VectorMatch(
                        record_id=row["record_id"],
                        distance=dist,
                        similarity=sim,
                        metadata=metadata,
                        payload=row["payload"],
                        namespace=row["namespace"],
                        provider_metadata={"backend": "pgvector", "table": self._table_name},
                    )
                )

        return matches

    async def count(self, namespace: str = "default") -> int:
        """Count total vector records in namespace."""
        pool = await self._get_pool()
        if pool is None:
            return await self._fallback.count(namespace=namespace)

        sql = f"SELECT COUNT(*) FROM {self._table_name} WHERE namespace = $1;"
        async with pool.acquire() as conn:
            return int(await conn.fetchval(sql, namespace))

    async def clear(self, namespace: str = "default") -> None:
        """Clear all vector records in target namespace."""
        pool = await self._get_pool()
        if pool is None:
            await self._fallback.clear(namespace=namespace)
            return

        sql = f"DELETE FROM {self._table_name} WHERE namespace = $1;"
        async with pool.acquire() as conn:
            await conn.execute(sql, namespace)

    async def health(self) -> dict[str, Any]:
        """Return health status dictionary."""
        await self._get_pool()
        return {
            "provider": self.capabilities.provider_name,
            "dimensions": self.capabilities.dimensions,
            "table": self._table_name,
            "healthy": True,
            "is_fallback": self._use_fallback,
            "index_type": self._index_type,
        }

    async def close(self) -> None:
        """Close connection pool."""
        if self._pool is not None and not self._use_fallback:
            try:
                await self._pool.close()
            except Exception as e:
                logger.debug(f"[PgVectorStore] Error closing pool: {e}")
            self._pool = None
