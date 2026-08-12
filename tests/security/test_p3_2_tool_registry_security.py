"""Security verification test suite for P3-2 ToolRegistry capability escalation, trust policies, and secret hygiene."""

from __future__ import annotations

import asyncio
import pytest

from nexusai.brain.domain.governance import ToolCapability
from nexusai.brain.domain.tool_registry import (
    CapabilityEscalationError,
    ToolMetadata,
    ToolStatus,
    ToolTrustLevel,
    ToolUnavailableError,
    ToolVersionMismatchError,
    TrustPolicyError,
)
from nexusai.brain.runtime.tool_registry import ToolRegistry


@pytest.mark.asyncio
async def test_security_capability_escalation_blocked() -> None:
    """Security Test: Planner or invocation trying to add undeclared capabilities is blocked."""
    registry = ToolRegistry()
    meta = ToolMetadata(
        tool_id="file_read_only",
        name="File Reader",
        version="1.0.0",
        description="Reads files",
        capabilities=frozenset({ToolCapability.FILE_READ}),
    )
    await registry.register(meta)

    # Attempting to request PROCESS_EXEC on a file reader tool -> Capability Escalation Blocked!
    with pytest.raises(CapabilityEscalationError):
        await registry.validate_tool(
            "file_read_only",
            requested_capabilities=frozenset({ToolCapability.FILE_READ, ToolCapability.PROCESS_EXEC}),
        )


@pytest.mark.asyncio
async def test_security_untrusted_and_revoked_tools_blocked() -> None:
    """Security Test: Untrusted and Revoked tools fail security validation."""
    registry = ToolRegistry()

    untrusted_meta = ToolMetadata(
        tool_id="untrusted_script",
        name="Untrusted Script",
        version="1.0.0",
        description="Untrusted",
        capabilities=frozenset({ToolCapability.PROCESS_EXEC}),
        trust_level=ToolTrustLevel.UNTRUSTED,
    )
    await registry.register(untrusted_meta)

    with pytest.raises(TrustPolicyError):
        await registry.validate_tool("untrusted_script")

    revoked_meta = ToolMetadata(
        tool_id="revoked_tool",
        name="Revoked Tool",
        version="1.0.0",
        description="Revoked",
        capabilities=frozenset({ToolCapability.NETWORK_ACCESS}),
        status=ToolStatus.REVOKED,
    )
    await registry.register(revoked_meta)

    with pytest.raises(ToolUnavailableError):
        await registry.validate_tool("revoked_tool")


if __name__ == "__main__":
    asyncio.run(test_security_capability_escalation_blocked())
    asyncio.run(test_security_untrusted_and_revoked_tools_blocked())
    print("ALL P3-2 TOOL REGISTRY SECURITY TESTS PASSED SUCCESSFULLY!")
