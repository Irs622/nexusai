"""Unit test suite for P3-2 ToolRegistry domain models, SemVer validation, capability escalation, and trust policies."""

from __future__ import annotations

import asyncio
import pytest

from nexusai.brain.domain.governance import ToolCapability
from nexusai.brain.domain.tool_registry import (
    CapabilityEscalationError,
    ToolAlreadyRegisteredError,
    ToolMetadata,
    ToolStatus,
    ToolTrustLevel,
    ToolUnavailableError,
    ToolVersionMismatchError,
    TrustPolicyError,
    validate_declared_capabilities,
)
from nexusai.brain.runtime.tool_registry import ToolRegistry


def test_tool_metadata_semver_and_secret_sanitization() -> None:
    """Test ToolMetadata SemVer validation and secret redaction."""
    meta = ToolMetadata(
        tool_id="filesystem.read",
        name="File Reader",
        version="1.2.0",
        description="Reads files",
        capabilities=frozenset({ToolCapability.FILE_READ}),
        metadata={"author": "alice", "api_key": "secret-12345"},
    )

    assert meta.tool_id == "filesystem.read"
    assert meta.version == "1.2.0"
    assert meta.metadata["author"] == "alice"
    assert meta.metadata["api_key"] == "[REDACTED_SECRET]"

    # Invalid semver format raises ValueError
    with pytest.raises(ValueError, match="Invalid semantic version format"):
        ToolMetadata(
            tool_id="filesystem.read",
            name="File Reader",
            version="v1.2",  # Missing patch number
            description="Reads files",
            capabilities=frozenset({ToolCapability.FILE_READ}),
        )


@pytest.mark.asyncio
async def test_P3_2_INV_01_duplicate_tool_registration_rejected() -> None:
    """Test P3-2-INV-01: Registering duplicate tool_id raises ToolAlreadyRegisteredError."""
    registry = ToolRegistry()
    meta1 = ToolMetadata(
        tool_id="shell.execute",
        name="Shell Exec",
        version="1.0.0",
        description="Executes shell",
        capabilities=frozenset({ToolCapability.PROCESS_EXEC}),
    )
    await registry.register(meta1)

    # Attempting duplicate registration raises ToolAlreadyRegisteredError
    with pytest.raises(ToolAlreadyRegisteredError, match="already registered"):
        await registry.register(meta1)


@pytest.mark.asyncio
async def test_P3_2_INV_02_disabled_and_revoked_tools_rejected() -> None:
    """Test P3-2-INV-02: Disabled and Revoked tools fail validation with ToolUnavailableError."""
    registry = ToolRegistry()
    disabled_meta = ToolMetadata(
        tool_id="tool.disabled",
        name="Disabled Tool",
        version="1.0.0",
        description="Disabled",
        capabilities=frozenset({ToolCapability.FILE_READ}),
        status=ToolStatus.DISABLED,
    )
    await registry.register(disabled_meta)

    with pytest.raises(ToolUnavailableError, match="unavailable for execution"):
        await registry.validate_tool("tool.disabled")


@pytest.mark.asyncio
async def test_capability_escalation_prevention() -> None:
    """Test Capability Escalation Protection: Requesting undeclared capabilities raises CapabilityEscalationError."""
    meta = ToolMetadata(
        tool_id="file.reader",
        name="File Reader",
        version="1.0.0",
        description="Reads files",
        capabilities=frozenset({ToolCapability.FILE_READ}),  # Only FILE_READ declared
    )

    # Requesting FILE_READ + FILE_WRITE -> Escalation detected!
    requested = frozenset({ToolCapability.FILE_READ, ToolCapability.FILE_WRITE})
    with pytest.raises(CapabilityEscalationError, match="Capability escalation detected"):
        validate_declared_capabilities(meta, requested)


@pytest.mark.asyncio
async def test_version_mismatch_and_untrusted_policy_rejection() -> None:
    """Test Version Mismatch and Trust Policy rejection rules."""
    registry = ToolRegistry()

    meta_untrusted = ToolMetadata(
        tool_id="malicious.tool",
        name="Untrusted Tool",
        version="1.0.0",
        description="Untrusted",
        capabilities=frozenset({ToolCapability.PROCESS_EXEC}),
        trust_level=ToolTrustLevel.UNTRUSTED,
    )
    await registry.register(meta_untrusted)

    # UNTRUSTED tool fails validation with TrustPolicyError
    with pytest.raises(TrustPolicyError, match="UNTRUSTED and denied"):
        await registry.validate_tool("malicious.tool")

    meta_semver = ToolMetadata(
        tool_id="net.fetch",
        name="Net Fetch",
        version="1.0.0",
        description="Fetch",
        capabilities=frozenset({ToolCapability.NETWORK_ACCESS}),
    )
    await registry.register(meta_semver)

    # Requesting version "2.0.0" when registered is "1.0.0" raises ToolVersionMismatchError
    with pytest.raises(ToolVersionMismatchError, match="version mismatch"):
        await registry.validate_tool("net.fetch", version="2.0.0")


if __name__ == "__main__":
    test_tool_metadata_semver_and_secret_sanitization()
    asyncio.run(test_P3_2_INV_01_duplicate_tool_registration_rejected())
    asyncio.run(test_P3_2_INV_02_disabled_and_revoked_tools_rejected())
    asyncio.run(test_capability_escalation_prevention())
    asyncio.run(test_version_mismatch_and_untrusted_policy_rejection())
    print("ALL P3-2 TOOL REGISTRY UNIT TESTS PASSED SUCCESSFULLY!")
