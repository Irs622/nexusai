"""
Unit tests for BackgroundWorkerManager.
"""

import asyncio

import pytest

from nexusai.kernel.worker import BackgroundWorkerManager


@pytest.mark.asyncio
async def test_background_worker_queue_processing():
    manager = BackgroundWorkerManager()
    processed_items: list[int] = []

    async def _handler(item: int):
        processed_items.append(item)

    manager.register_worker("int_worker", _handler)
    manager.start()

    manager.enqueue_job("int_worker", 10)
    manager.enqueue_job("int_worker", 20)
    manager.enqueue_job("int_worker", 30)

    await asyncio.sleep(0.05)

    workers = manager.list_workers()
    assert len(workers) == 1
    assert workers[0]["processed_count"] == 3
    assert processed_items == [10, 20, 30]

    await manager.stop()
    assert manager.is_active is False


@pytest.mark.asyncio
async def test_background_worker_exception_isolation():
    manager = BackgroundWorkerManager()

    async def _failing_handler(item: str):
        if item == "fail":
            raise RuntimeError("Worker queue processing failed")

    manager.register_worker("fail_worker", _failing_handler)
    manager.start()

    manager.enqueue_job("fail_worker", "ok")
    manager.enqueue_job("fail_worker", "fail")
    manager.enqueue_job("fail_worker", "ok2")

    await asyncio.sleep(0.05)

    workers = manager.list_workers()
    meta = workers[0]
    assert meta["processed_count"] == 3
    assert meta["errors_count"] == 1
    assert "Worker queue processing failed" in meta["last_error"]

    await manager.stop()
