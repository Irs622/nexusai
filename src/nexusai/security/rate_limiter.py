"""Pluggable sliding-window rate limiters for API key authentication.

``InMemoryRateLimiter`` is process-local: with N workers or replicas the effective
aggregate limit is roughly N × the configured limit, and counters reset on restart.
Multi-worker / multi-replica deployments should set ``NEXUSAI_REDIS_URL`` (or
``REDIS_URL``) so ``create_rate_limiter()`` returns a shared ``RedisRateLimiter``.
"""

from __future__ import annotations

import os
import threading
import time
import uuid
from abc import ABC, abstractmethod
from typing import Any

from nexusai.core.errors import ConfigurationError
from nexusai.logging.logger import logger


class IRateLimiter(ABC):
    """Sliding-window request limiter keyed by an opaque identifier."""

    @abstractmethod
    def try_acquire(self, key: str, limit: int, window_seconds: float = 60.0) -> bool:
        """Record one request for ``key`` if it fits within ``limit`` per window.

        Returns:
            True if the request is allowed (and counted), False if the limit is reached.
        """
        ...


class InMemoryRateLimiter(IRateLimiter):
    """Process-local limiter. Suitable only for single-process deployments and tests."""

    def __init__(self) -> None:
        self._hits: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def try_acquire(self, key: str, limit: int, window_seconds: float = 60.0) -> bool:
        now = time.time()
        cutoff = now - window_seconds
        with self._lock:
            recent = [t for t in self._hits.get(key, []) if t > cutoff]
            if len(recent) >= limit:
                self._hits[key] = recent
                return False
            recent.append(now)
            self._hits[key] = recent
            return True


class RedisRateLimiter(IRateLimiter):
    """Redis sorted-set sliding window shared by every worker and replica.

    Each request adds a unique member scored by its timestamp inside a MULTI/EXEC
    transaction that also trims expired members and counts the window. A request
    that pushes the count over the limit removes its own member and is rejected, so
    concurrent replicas can never admit more than ``limit`` requests per window.
    """

    KEY_PREFIX = "nexusai:ratelimit:"

    def __init__(
        self, redis_url: str | None = None, client: Any = None, fail_open: bool = True
    ) -> None:
        """Create a Redis-backed limiter.

        Args:
            redis_url: Redis connection URL (ignored when ``client`` is given).
            client: Pre-built synchronous redis client (mainly for tests).
            fail_open: When Redis is unreachable, allow requests (logging an error)
                instead of rejecting every client.
        """
        if redis_url is None and client is None:
            raise ConfigurationError("RedisRateLimiter requires redis_url or client")
        self.redis_url = redis_url
        self.fail_open = fail_open
        self._client = client
        self._lock = threading.Lock()

    def _get_client(self) -> Any:
        if self._client is None:
            with self._lock:
                if self._client is None:
                    try:
                        import redis
                    except ImportError as err:
                        raise ConfigurationError(
                            "redis-py is required for RedisRateLimiter. Install with `pip install redis`."
                        ) from err
                    self._client = redis.Redis.from_url(
                        self.redis_url, decode_responses=True, socket_timeout=0.5
                    )
        return self._client

    def try_acquire(self, key: str, limit: int, window_seconds: float = 60.0) -> bool:
        redis_key = f"{self.KEY_PREFIX}{key}"
        now = time.time()
        member = f"{now:.6f}:{uuid.uuid4().hex}"
        try:
            client = self._get_client()
            pipe = client.pipeline(transaction=True)
            pipe.zremrangebyscore(redis_key, 0, now - window_seconds)
            pipe.zadd(redis_key, {member: now})
            pipe.zcard(redis_key)
            pipe.expire(redis_key, int(window_seconds) + 1)
            _, _, count, _ = pipe.execute()
            if int(count) > limit:
                client.zrem(redis_key, member)
                return False
            return True
        except ConfigurationError:
            raise
        except Exception as exc:
            logger.error(
                "Rate limiter backend unavailable ({}); {} request for key {}",
                type(exc).__name__,
                "allowing" if self.fail_open else "rejecting",
                key[:12],
            )
            return self.fail_open


def create_rate_limiter() -> IRateLimiter:
    """Build the rate limiter for this deployment from environment configuration."""
    redis_url = os.getenv("NEXUSAI_REDIS_URL") or os.getenv("REDIS_URL")
    if redis_url:
        logger.info("Using RedisRateLimiter for distributed API rate limiting")
        return RedisRateLimiter(redis_url)

    is_production = os.getenv("NEXUSAI_ENV") in ("production", "prod")
    replicas = int(os.getenv("NEXUSAI_REPLICAS", "1"))
    if is_production or replicas > 1:
        logger.warning(
            "API rate limiting is process-local (no NEXUSAI_REDIS_URL configured): each "
            "worker/replica enforces the limit independently and counters reset on restart."
        )
    return InMemoryRateLimiter()
