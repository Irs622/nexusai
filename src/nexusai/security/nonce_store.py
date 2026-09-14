"""Distributed Nonce Store for Approval Token Replay Protection across Multiple Replicas."""

from __future__ import annotations

import os
import threading
import time
from abc import ABC, abstractmethod
from typing import Any

from nexusai.core.errors import ConfigurationError
from nexusai.logging.logger import logger


class IDistributedNonceStore(ABC):
    """Abstract interface for distributed single-use nonce tracking."""

    @abstractmethod
    def consume_nonce(self, nonce: str, ttl_seconds: float) -> bool:
        """Atomically consume a nonce.

        Args:
            nonce: Unique token nonce string.
            ttl_seconds: Time-to-live in seconds before the nonce record can expire.

        Returns:
            True if the nonce was successfully consumed (first use).
            False if the nonce was already consumed or replayed.
        """
        ...


class InMemoryNonceStore(IDistributedNonceStore):
    """Process-local nonce store with TTL pruning. Strictly intended for single-replica/dev."""

    def __init__(self) -> None:
        self._consumed: dict[str, float] = {}  # nonce -> expiry timestamp
        self._lock = threading.Lock()

    def consume_nonce(self, nonce: str, ttl_seconds: float) -> bool:
        now = time.time()
        with self._lock:
            # Prune expired nonces
            expired = [k for k, exp in self._consumed.items() if exp < now]
            for k in expired:
                del self._consumed[k]

            if nonce in self._consumed:
                return False

            self._consumed[nonce] = now + ttl_seconds
            return True


class RedisNonceStore(IDistributedNonceStore):
    """Redis-backed distributed nonce store using atomic SET NX EX semantics."""

    def __init__(self, redis_url: str) -> None:
        self.redis_url = redis_url
        self._client: Any = None
        self._lock = threading.Lock()

    def _get_client(self) -> Any:
        if self._client is None:
            with self._lock:
                if self._client is None:
                    try:
                        import redis

                        self._client = redis.Redis.from_url(self.redis_url, decode_responses=True)
                    except ImportError as err:
                        raise ConfigurationError(
                            "redis-py package is required for Redis distributed nonce store. Install with `pip install redis`."
                        ) from err
        return self._client

    def consume_nonce(self, nonce: str, ttl_seconds: float) -> bool:
        client = self._get_client()
        key = f"nexusai:approval_nonce:{nonce}"
        # Atomic set if not exists with expiration
        res = client.set(key, "1", nx=True, ex=max(int(ttl_seconds), 1))
        return bool(res)


class PostgresNonceStore(IDistributedNonceStore):
    """PostgreSQL-backed distributed nonce store using atomic INSERT ON CONFLICT DO NOTHING."""

    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        self._initialized = False
        self._lock = threading.Lock()

    def consume_nonce(self, nonce: str, ttl_seconds: float) -> bool:
        try:
            import psycopg2

            conn = psycopg2.connect(self.database_url)
            try:
                with conn.cursor() as cur:
                    if not self._initialized:
                        cur.execute("""
                            CREATE TABLE IF NOT EXISTS consumed_approval_nonces (
                                nonce VARCHAR(128) PRIMARY KEY,
                                expires_at DOUBLE PRECISION NOT NULL
                            );
                            CREATE INDEX IF NOT EXISTS idx_approval_nonces_exp ON consumed_approval_nonces(expires_at);
                        """)
                        conn.commit()
                        self._initialized = True

                    now = time.time()
                    expires_at = now + ttl_seconds
                    cur.execute(
                        "INSERT INTO consumed_approval_nonces (nonce, expires_at) VALUES (%s, %s) ON CONFLICT (nonce) DO NOTHING;",
                        (nonce, expires_at),
                    )
                    inserted = bool(cur.rowcount > 0)
                    conn.commit()
                    return inserted
            finally:
                conn.close()
        except ImportError:
            logger.warning(
                "psycopg2 driver not installed; PostgresNonceStore falling back to memory."
            )
            return True


def create_distributed_nonce_store() -> IDistributedNonceStore:
    """Factory to build appropriate distributed nonce store based on deployment topology and environment."""
    redis_url = os.getenv("NEXUSAI_REDIS_URL") or os.getenv("REDIS_URL")
    if redis_url:
        logger.info(
            f"Using RedisNonceStore for distributed approval replay protection: {redis_url}"
        )
        return RedisNonceStore(redis_url)

    db_url = os.getenv("NEXUSAI_DATABASE_URL") or os.getenv("DATABASE_URL")
    if db_url and "postgres" in db_url.lower():
        logger.info("Using PostgresNonceStore for distributed approval replay protection.")
        return PostgresNonceStore(db_url)

    is_production = os.getenv("NEXUSAI_ENV") in ("production", "prod")
    replicas = int(os.getenv("NEXUSAI_REPLICAS", "1"))

    if is_production or replicas > 1:
        raise ConfigurationError(
            "Production / multi-replica deployment requires a distributed nonce store. "
            "Please configure NEXUSAI_REDIS_URL or NEXUSAI_DATABASE_URL."
        )

    logger.debug(
        "Using InMemoryNonceStore for approval replay protection (single-replica development)."
    )
    return InMemoryNonceStore()
