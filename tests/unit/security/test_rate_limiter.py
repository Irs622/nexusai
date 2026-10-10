"""AUDIT-15: rate limits must be shareable across workers/replicas."""

from __future__ import annotations

import os
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pytest

from nexusai.core.errors import RateLimitExceededError
from nexusai.security.authentication import ApiKeyService
from nexusai.security.identity import Role
from nexusai.security.rate_limiter import (
    InMemoryRateLimiter,
    RedisRateLimiter,
    create_rate_limiter,
)


class FakeRedisServer:
    """Minimal thread-safe stand-in for the sorted-set commands RedisRateLimiter uses."""

    def __init__(self) -> None:
        self.zsets: dict[str, dict[str, float]] = {}
        self.lock = threading.Lock()


class FakeRedisClient:
    def __init__(self, server: FakeRedisServer) -> None:
        self.server = server

    def pipeline(self, transaction: bool = True) -> FakePipeline:
        return FakePipeline(self.server)

    def zrem(self, key: str, member: str) -> int:
        with self.server.lock:
            return int(self.server.zsets.get(key, {}).pop(member, None) is not None)


class FakePipeline:
    def __init__(self, server: FakeRedisServer) -> None:
        self.server = server
        self.ops: list[tuple[str, tuple[Any, ...]]] = []

    def zremrangebyscore(self, key: str, lo: float, hi: float) -> None:
        self.ops.append(("zremrangebyscore", (key, lo, hi)))

    def zadd(self, key: str, mapping: dict[str, float]) -> None:
        self.ops.append(("zadd", (key, mapping)))

    def zcard(self, key: str) -> None:
        self.ops.append(("zcard", (key,)))

    def expire(self, key: str, seconds: int) -> None:
        self.ops.append(("expire", (key, seconds)))

    def execute(self) -> list[Any]:
        results: list[Any] = []
        with self.server.lock:  # MULTI/EXEC: all ops apply atomically
            for op, args in self.ops:
                zset = self.server.zsets.setdefault(args[0], {})
                if op == "zremrangebyscore":
                    stale = [m for m, sc in zset.items() if args[1] <= sc <= args[2]]
                    for m in stale:
                        del zset[m]
                    results.append(len(stale))
                elif op == "zadd":
                    zset.update(args[1])
                    results.append(len(args[1]))
                elif op == "zcard":
                    results.append(len(zset))
                else:
                    results.append(True)
        return results


class BrokenClient:
    def pipeline(self, transaction: bool = True) -> Any:
        raise ConnectionError("redis down")


def _replica(limiter: Any, raw_key: str) -> ApiKeyService:
    service = ApiKeyService(rate_limiter=limiter)
    service.register_raw_key(
        raw_key, tenant_id="t1", user_id="u1", role=Role.OPERATOR, rate_limit_per_minute=5
    )
    return service


def test_in_memory_limiter_enforces_window() -> None:
    limiter = InMemoryRateLimiter()
    assert all(limiter.try_acquire("k", 3) for _ in range(3))
    assert limiter.try_acquire("k", 3) is False


def test_replicas_sharing_redis_enforce_one_aggregate_limit() -> None:
    server = FakeRedisServer()
    raw_key = "nx_rate_limit_shared_example"
    replica_a = _replica(RedisRateLimiter(client=FakeRedisClient(server)), raw_key)
    replica_b = _replica(RedisRateLimiter(client=FakeRedisClient(server)), raw_key)

    allowed = 0
    for i in range(10):
        try:
            (replica_a if i % 2 == 0 else replica_b).authenticate(raw_key)
            allowed += 1
        except RateLimitExceededError:
            pass
    assert allowed == 5


def test_process_local_limiters_do_not_share_state() -> None:
    """Documents the AUDIT-15 failure mode the Redis backend fixes."""
    raw_key = "nx_rate_limit_local_example"
    replica_a = _replica(InMemoryRateLimiter(), raw_key)
    replica_b = _replica(InMemoryRateLimiter(), raw_key)
    for _ in range(5):
        replica_a.authenticate(raw_key)
        replica_b.authenticate(raw_key)  # each replica admits 5 → 10 total


def test_concurrent_acquires_never_exceed_limit() -> None:
    server = FakeRedisServer()
    limiters = [RedisRateLimiter(client=FakeRedisClient(server)) for _ in range(4)]
    with ThreadPoolExecutor(max_workers=16) as pool:
        results = list(pool.map(lambda i: limiters[i % 4].try_acquire("hot", 20), range(200)))
    assert sum(results) == 20


def test_redis_outage_fails_open_by_default_and_closed_when_configured() -> None:
    assert RedisRateLimiter(client=BrokenClient()).try_acquire("k", 1) is True
    assert RedisRateLimiter(client=BrokenClient(), fail_open=False).try_acquire("k", 1) is False


def test_factory_selects_backend_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NEXUSAI_REDIS_URL", raising=False)
    monkeypatch.delenv("REDIS_URL", raising=False)
    assert isinstance(create_rate_limiter(), InMemoryRateLimiter)
    monkeypatch.setenv("NEXUSAI_REDIS_URL", "redis://localhost:6379/0")
    assert isinstance(create_rate_limiter(), RedisRateLimiter)


@pytest.mark.network
@pytest.mark.skipif(not os.getenv("NEXUSAI_TEST_REDIS_URL"), reason="needs a live Redis")
def test_live_redis_shared_limit() -> None:
    url = os.environ["NEXUSAI_TEST_REDIS_URL"]
    a, b = RedisRateLimiter(url), RedisRateLimiter(url)
    key = f"live-test-{os.getpid()}"
    results = [(a if i % 2 else b).try_acquire(key, 3) for i in range(6)]
    assert sum(results) == 3
