"""
Background Worker Manager for queue-based task execution in NexusAI OS Kernel.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from nexusai.logging.logger import logger


@dataclass
class WorkerMeta:
    """Metadata tracking background queue worker status."""

    name: str
    processed_count: int = 0
    errors_count: int = 0
    last_processed_at: str | None = None
    last_error: str | None = None
    is_running: bool = False


class BackgroundWorkerManager:
    """Manager for queue-based background workers executing items from asyncio queues."""

    def __init__(self) -> None:
        self._workers: dict[str, asyncio.Task[Any]] = {}
        self._queues: dict[str, asyncio.Queue[Any]] = {}
        self._handlers: dict[str, Callable[[Any], Awaitable[None]]] = {}
        self._meta: dict[str, WorkerMeta] = {}
        self._is_active: bool = False

    @property
    def is_active(self) -> bool:
        """Return True if background worker manager is active."""
        return self._is_active

    def register_worker(
        self,
        name: str,
        handler: Callable[[Any], Awaitable[None]],
        queue: asyncio.Queue[Any] | None = None,
    ) -> asyncio.Queue[Any]:
        """Register a queue worker with a handler function."""
        if name in self._meta:
            logger.warning(f"Worker '{name}' is already registered. Overwriting handler...")

        q = queue or asyncio.Queue()
        self._queues[name] = q
        self._handlers[name] = handler
        self._meta[name] = WorkerMeta(name=name)

        if self._is_active:
            self._start_worker_loop(name)

        return q

    def enqueue_job(self, worker_name: str, item: Any) -> None:
        """Enqueue an item into the queue of worker_name."""
        if worker_name not in self._queues:
            raise KeyError(f"No background worker registered with name '{worker_name}'")
        self._queues[worker_name].put_nowait(item)

    def start(self) -> None:
        """Start all registered queue workers."""
        if self._is_active:
            return
        self._is_active = True
        logger.info("Starting BackgroundWorkerManager...")

        for name in self._handlers:
            self._start_worker_loop(name)

    async def stop(self, drain_timeout: float = 2.0) -> None:
        """Stop all workers, optionally allowing pending queue items to drain."""
        self._is_active = False
        logger.info("Stopping BackgroundWorkerManager...")

        # Wait for queues to drain up to drain_timeout
        drain_tasks = [q.join() for q in self._queues.values()]
        if drain_tasks:
            try:
                await asyncio.wait_for(asyncio.gather(*drain_tasks, return_exceptions=True), timeout=drain_timeout)
            except asyncio.TimeoutError:
                logger.warning(f"Worker queue drain timed out after {drain_timeout}s.")

        for name, task in list(self._workers.items()):
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            if name in self._meta:
                self._meta[name].is_running = False

        self._workers.clear()
        logger.info("BackgroundWorkerManager stopped.")

    def list_workers(self) -> list[dict[str, Any]]:
        """Return metrics and state of all registered background workers."""
        return [
            {
                "name": meta.name,
                "processed_count": meta.processed_count,
                "errors_count": meta.errors_count,
                "queue_size": self._queues[meta.name].qsize() if meta.name in self._queues else 0,
                "last_processed_at": meta.last_processed_at,
                "last_error": meta.last_error,
                "is_running": meta.is_running and (meta.name in self._workers and not self._workers[meta.name].done()),
            }
            for meta in self._meta.values()
        ]

    def _start_worker_loop(self, name: str) -> None:
        """Spawn the async queue listener loop for worker name."""
        handler = self._handlers[name]
        queue = self._queues[name]
        meta = self._meta[name]
        meta.is_running = True

        async def _worker_loop() -> None:
            while self._is_active:
                try:
                    item = await queue.get()
                except asyncio.CancelledError:
                    break

                try:
                    meta.processed_count += 1
                    meta.last_processed_at = datetime.now(timezone.utc).isoformat()
                    await handler(item)
                except asyncio.CancelledError:
                    queue.task_done()
                    raise
                except Exception as err:
                    meta.errors_count += 1
                    meta.last_error = str(err)
                    logger.error(f"Error in background worker '{name}': {err}")
                finally:
                    queue.task_done()

        self._workers[name] = asyncio.create_task(_worker_loop(), name=f"worker_{name}")
