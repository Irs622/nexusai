"""Adversarial stress test suite for P3-2 ToolRegistry concurrency safety and atomic operations."""

from __future__ import annotations

import asyncio
import time
import pytest

from nexusai.brain.domain.governance import ToolCapability
from nexusai.brain.domain.tool_registry import (
    ToolAlreadyRegisteredError,
    ToolMetadata,
    ToolStatus,
    ToolTrustLevel,
)
from nexusai.brain.runtime.tool_registry import ToolRegistry


@pytest.mark.asyncio
async def test_p3_2_adversarial_tool_registry_stress() -> None:
    """Stress Test: 20 concurrent workers registering, looking up, and validating 50+ tools with 1,000+ operations.

    Invariants: No registry corruption, no duplicate tool IDs, thread/task safe.
    """
    registry = ToolRegistry()

    # Pre-register 30 base tools
    for i in range(30):
        meta = ToolMetadata(
            tool_id=f"base.tool.{i}",
            name=f"Base Tool {i}",
            version="1.0.0",
            description=f"Base Tool Description {i}",
            capabilities=frozenset({ToolCapability.FILE_READ}),
        )
        await registry.register(meta)

    async def worker(worker_id: int, count: int) -> None:
        for i in range(count):
            # Concurrent registration of worker-specific tool
            t_id = f"worker.{worker_id}.tool.{i}"
            meta = ToolMetadata(
                tool_id=t_id,
                name=f"Worker Tool {t_id}",
                version="1.0.0",
                description="Worker Tool",
                capabilities=frozenset({ToolCapability.NETWORK_ACCESS}),
            )
            try:
                await registry.register(meta)
            except ToolAlreadyRegisteredError:
                pass

            # Concurrent validation of base tool
            base_id = f"base.tool.{(worker_id + i) % 30}"
            val_meta = await registry.validate_tool(base_id)
            assert val_meta.tool_id == base_id

            # Concurrent listing
            tools = await registry.list_tools(capability=ToolCapability.FILE_READ)
            assert len(tools) >= 30

            await asyncio.sleep(0.001)

    # Launch 20 concurrent workers executing 50 operations each (1,000 total operations)
    workers = [asyncio.create_task(worker(w, 50)) for w in range(20)]
    await asyncio.gather(*workers)

    final_tools = await registry.list_tools()
    print(f"\n[P3-2 ADVERSARIAL REGISTRY STRESS VERIFICATION]")
    print(f"Total Active Registered Tools: {len(final_tools)}")

    assert len(final_tools) >= 1030
    assert len(set(m.tool_id for m in final_tools)) == len(final_tools), "Duplicate tool_ids detected in registry!"


if __name__ == "__main__":
    asyncio.run(test_p3_2_adversarial_tool_registry_stress())
    print("ALL P3-2 TOOL REGISTRY INTEGRATION & STRESS TESTS PASSED SUCCESSFULLY!")
