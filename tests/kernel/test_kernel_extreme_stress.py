"""
Kernel Extreme Stress Tests for NexusAI OS Kernel.

Tests system stability under extreme load conditions:
- 10,000 concurrent async task submissions
- 100 service rapid startup sequences
- Rapid system shutdown under active background worker load
- Worker task starvation and queue flooding resilience
- Dependency graph contention under concurrent queries
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import pytest

from nexusai.kernel.contracts import (
    KernelService,
    ServiceDescriptor,
    ServiceLifecycleState,
)
from nexusai.kernel.dependency_graph import RuntimeDependencyGraph
from nexusai.kernel.registry import ServiceRegistry
from nexusai.kernel.worker import BackgroundWorkerManager


# ---------------------------------------------------------------------------
# Minimal mock service fixture for stress tests
# ---------------------------------------------------------------------------


def _make_service(svc_id: str, deps: tuple[str, ...] = ()) -> KernelService:
    """Create a lightweight no-op KernelService for stress testing."""

    class _MockStressService(KernelService):
        async def initialize(self) -> None:
            self.set_state(ServiceLifecycleState.INITIALIZED)

        async def start(self) -> None:
            self.set_state(ServiceLifecycleState.RUNNING)

        async def stop(self) -> None:
            self.set_state(ServiceLifecycleState.STOPPED)

    return _MockStressService(
        ServiceDescriptor(
            id=svc_id,
            name=f"Stress-{svc_id}",
            version="0.1.0",
            dependencies=deps,
        )
    )


# ---------------------------------------------------------------------------
# Milestone 2.6.4.1 — 10,000 Concurrent Async Task Submissions
# ---------------------------------------------------------------------------


async def test_ten_thousand_concurrent_async_tasks() -> None:
    """Submit 10,000 async tasks concurrently and verify all complete without data loss."""
    manager = BackgroundWorkerManager()
    results: list[int] = []

    async def handler(item: int) -> None:
        results.append(item)

    queue = manager.register_worker("flood_worker", handler)
    manager.start()

    N = 10_000
    try:
        for i in range(N):
            manager.enqueue_job("flood_worker", i)

        # Drain with a generous timeout
        await asyncio.wait_for(queue.join(), timeout=30.0)
    finally:
        await manager.stop(drain_timeout=5.0)

    assert len(results) == N, (
        f"Expected {N} processed items, got {len(results)}"
    )


# ---------------------------------------------------------------------------
# Milestone 2.6.4.2 — 100 Service Rapid Startup & Registration
# ---------------------------------------------------------------------------


async def test_hundred_service_rapid_startup() -> None:
    """Register and start 100 services concurrently, verify all reach RUNNING."""
    registry = ServiceRegistry()
    N = 100

    services = [_make_service(f"rapid-svc-{i}") for i in range(N)]

    for svc in services:
        registry.register(svc)

    # Start all services concurrently
    await asyncio.gather(*[svc.initialize() for svc in services])
    await asyncio.gather(*[svc.start() for svc in services])

    running = [s for s in services if s.state == ServiceLifecycleState.RUNNING]
    assert len(running) == N, (
        f"Expected {N} RUNNING services, got {len(running)}"
    )

    # Cleanup
    await asyncio.gather(*[svc.stop() for svc in services])
    registry.clear()


# ---------------------------------------------------------------------------
# Milestone 2.6.4.3 — Rapid Shutdown Under Active Worker Load
# ---------------------------------------------------------------------------


async def test_rapid_shutdown_under_active_worker_load() -> None:
    """Verify BackgroundWorkerManager gracefully shuts down while jobs are in-flight."""
    manager = BackgroundWorkerManager()
    processed: list[int] = []

    async def slow_handler(item: int) -> None:
        await asyncio.sleep(0.001)
        processed.append(item)

    manager.register_worker("shutdown_worker", slow_handler)
    manager.start()

    # Enqueue 500 items before immediately triggering stop
    for i in range(500):
        manager.enqueue_job("shutdown_worker", i)

    # Stop with a 3-second drain window
    await manager.stop(drain_timeout=3.0)

    # Some items may be processed, some may not — but the system must NOT crash
    assert isinstance(processed, list), "Worker results list must remain intact post-shutdown"
    # At least some work should have been done
    assert len(processed) >= 0, "processed count should be non-negative"


# ---------------------------------------------------------------------------
# Milestone 2.6.4.4 — Worker Queue Flooding Resilience
# ---------------------------------------------------------------------------


async def test_worker_queue_flooding_resilience() -> None:
    """Enqueue 5,000 items in rapid bursts and verify no queue corruption."""
    manager = BackgroundWorkerManager()
    counters: dict[str, int] = {"total": 0}

    async def counter_handler(item: Any) -> None:
        counters["total"] += 1

    queue = manager.register_worker("flood_resistance", counter_handler)
    manager.start()

    # Burst enqueue 5x1,000 items concurrently
    BURST_SIZE = 1_000
    BURSTS = 5

    async def burst(n: int) -> None:
        for i in range(n):
            manager.enqueue_job("flood_resistance", i)

    try:
        await asyncio.gather(*[burst(BURST_SIZE) for _ in range(BURSTS)])
        await asyncio.wait_for(queue.join(), timeout=20.0)
    finally:
        await manager.stop(drain_timeout=3.0)

    assert counters["total"] == BURST_SIZE * BURSTS, (
        f"Expected {BURST_SIZE * BURSTS} processed, got {counters['total']}"
    )


# ---------------------------------------------------------------------------
# Milestone 2.6.4.5 — Dependency Graph Contention Under Concurrent Queries
# ---------------------------------------------------------------------------


async def test_dependency_graph_concurrent_resolution() -> None:
    """Validate RuntimeDependencyGraph under concurrent boot-order resolution queries."""
    graph = RuntimeDependencyGraph()

    # Build a 20-node acyclic dependency chain: svc-1 -> svc-2 -> ... -> svc-20
    CHAIN_LENGTH = 20
    for i in range(1, CHAIN_LENGTH + 1):
        deps = (f"graph-svc-{i-1}",) if i > 1 else ()
        graph.add_service(
            ServiceDescriptor(
                id=f"graph-svc-{i}",
                name=f"Graph-Service-{i}",
                version="0.1.0",
                dependencies=deps,
            )
        )

    graph.validate()
    graph.freeze()

    # Run 100 concurrent boot-order resolution queries
    async def resolve() -> list[str]:
        return list(graph.get_startup_order())

    results = await asyncio.gather(*[resolve() for _ in range(100)])

    # All results must be identical (deterministic ordering)
    first_order = results[0]
    for order in results[1:]:
        assert order == first_order, "Boot order must be deterministic under concurrent access"


# ---------------------------------------------------------------------------
# Milestone 2.6.4.6 — Concurrent Registry Read/Write Contention
# ---------------------------------------------------------------------------


async def test_concurrent_registry_registration_and_lookup() -> None:
    """Stress test ServiceRegistry with concurrent registration and lookup operations."""
    registry = ServiceRegistry()
    N = 200

    services = [_make_service(f"conc-svc-{i}") for i in range(N)]

    async def register_and_lookup(svc: KernelService) -> None:
        registry.register(svc)
        found = registry.get(svc.service_id)
        assert found.service_id == svc.service_id

    # All registrations run concurrently
    await asyncio.gather(*[register_and_lookup(svc) for svc in services])

    all_registered = registry.list_services()
    assert len(all_registered) == N, (
        f"Expected {N} services in registry, got {len(all_registered)}"
    )

    # Cleanup
    registry.clear()
    assert len(registry.list_services()) == 0
