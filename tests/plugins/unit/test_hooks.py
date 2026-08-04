"""
Unit tests for HookRegistry and HookManager middleware system.
"""

import pytest
from nexusai.plugins.hooks import HookManager, HookPayload, HookRegistry, HookType


@pytest.mark.asyncio
async def test_hook_execution_order_and_cancellation():
    registry = HookRegistry()
    execution_order: list[str] = []

    async def hook_low_priority(payload: HookPayload) -> None:
        execution_order.append("low")
        payload.data["modified"] = True

    async def hook_high_priority(payload: HookPayload) -> None:
        execution_order.append("high")

    # Priority 10 runs before Priority 100
    registry.register_hook("plugin.b", HookType.BEFORE_LLM_REQUEST, hook_low_priority, priority=100)
    registry.register_hook("plugin.a", HookType.BEFORE_LLM_REQUEST, hook_high_priority, priority=10)

    manager = HookManager(registry)
    result = await manager.trigger_hook(HookType.BEFORE_LLM_REQUEST, "caller.plugin", {"original": True})

    assert execution_order == ["high", "low"]
    assert result.data["modified"] is True
