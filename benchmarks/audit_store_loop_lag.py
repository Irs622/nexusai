"""Measure asyncio event-loop responsiveness while SQLiteAuditStore absorbs concurrent writes.

A probe coroutine sleeps for a fixed interval in a loop and records how late it wakes
up. The lateness stands in for the latency a cheap endpoint such as ``/health/live``
would see. Usage::

    python -m benchmarks.audit_store_loop_lag [--writes 400] [--concurrency 50]
"""

from __future__ import annotations

import argparse
import asyncio
import statistics
import tempfile
import time
from pathlib import Path

from nexusai.brain.domain.audit import AuditEvent
from nexusai.infrastructure.persistence.sqlite_audit_store import SQLiteAuditStore

PROBE_INTERVAL_S = 0.001


async def measure_loop_lag(
    store: SQLiteAuditStore, writes: int, concurrency: int
) -> dict[str, float]:
    """Run concurrent audit appends and return probe lateness percentiles in ms."""
    lags_ms: list[float] = []
    done = asyncio.Event()

    async def probe() -> None:
        while not done.is_set():
            start = time.perf_counter()
            await asyncio.sleep(PROBE_INTERVAL_S)
            lags_ms.append((time.perf_counter() - start - PROBE_INTERVAL_S) * 1000.0)

    sem = asyncio.Semaphore(concurrency)

    async def write(i: int) -> None:
        async with sem:
            await store.append_event(
                AuditEvent(
                    event_id=f"bench-{i}",
                    event_type="BENCH",
                    session_id="bench",
                    execution_id="bench",
                    plan_fingerprint="bench",
                    sequence_number=0,
                    outcome="SUCCESS",
                )
            )

    probe_task = asyncio.create_task(probe())
    await asyncio.sleep(0.01)
    await asyncio.gather(*(write(i) for i in range(writes)))
    done.set()
    await probe_task

    ordered = sorted(lags_ms)

    def pct(q: float) -> float:
        return ordered[min(len(ordered) - 1, int(q * len(ordered)))]

    return {
        "samples": float(len(ordered)),
        "p50_ms": statistics.median(ordered),
        "p95_ms": pct(0.95),
        "p99_ms": pct(0.99),
        "max_ms": ordered[-1],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--writes", type=int, default=400)
    parser.add_argument("--concurrency", type=int, default=50)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        store = SQLiteAuditStore(db_path=str(Path(tmp) / "audit.db"))
        result = asyncio.run(measure_loop_lag(store, args.writes, args.concurrency))
    print(" ".join(f"{k}={v:.2f}" for k, v in result.items()))  # noqa: T201 - CLI benchmark output


if __name__ == "__main__":
    main()
