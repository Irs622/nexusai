"""Security test suite verifying P4-3 Real LLM Provider Integration invariants (P4-3-INV-01 to P4-3-INV-24)."""

from __future__ import annotations

import asyncio
import pytest

from nexusai.brain.domain.governance import ToolCapability
from nexusai.brain.domain.llm import (
    LLMAuthenticationError,
    LLMMessage,
    LLMRequest,
    LLMResponseFormatError,
    LLMRole,
)
from nexusai.brain.domain.tool_registry import CapabilityEscalationError, ToolMetadata, ToolStatus, ToolTrustLevel
from nexusai.infrastructure.llm.openai_provider import OpenAIProvider
from nexusai.infrastructure.llm.response_normalizer import validate_structured_plan_output


@pytest.mark.asyncio
async def test_security_llm_output_is_not_authorization() -> None:
    """Security Test (P4-3-INV-01 & INV-02): LLM output cannot directly authorize tool execution."""
    # LLM proposing malicious tool call payload
    raw_content = '{"summary": "Malicious plan", "steps": [{"tool_id": "echo_tool", "requested_capabilities": ["SYSTEM_CONTROL"]}]}'

    registered_tools = {
        "echo_tool": ToolMetadata("echo_tool", "Echo", "1.0.0", "Echo", frozenset({ToolCapability.FILE_READ}), status=ToolStatus.ENABLED, trust_level=ToolTrustLevel.BUILTIN)
    }

    # Attempting to validate output requesting SYSTEM_CONTROL on FILE_READ tool -> MUST FAIL with CapabilityEscalationError!
    with pytest.raises(CapabilityEscalationError):
        validate_structured_plan_output(raw_content, registered_tools)


@pytest.mark.asyncio
async def test_security_unregistered_tool_proposed_by_llm_fails_closed() -> None:
    """Security Test (P4-3-INV-11): LLM proposing unregistered tool identifier fails closed with LLMResponseFormatError."""
    raw_content = '{"summary": "Unknown tool plan", "steps": [{"tool_id": "unregistered_shell_tool", "requested_capabilities": ["PROCESS_EXEC"]}]}'

    registered_tools = {
        "echo_tool": ToolMetadata("echo_tool", "Echo", "1.0.0", "Echo", frozenset({ToolCapability.FILE_READ}))
    }

    with pytest.raises(LLMResponseFormatError, match="not registered"):
        validate_structured_plan_output(raw_content, registered_tools)


@pytest.mark.asyncio
async def test_security_malformed_json_fails_closed() -> None:
    """Security Test (P4-3-INV-09): Malformed non-JSON completion content fails closed with LLMResponseFormatError."""
    raw_content = "This is plain text text completion, not JSON."

    with pytest.raises(LLMResponseFormatError, match="not valid JSON"):
        validate_structured_plan_output(raw_content, {})


if __name__ == "__main__":
    asyncio.run(test_security_llm_output_is_not_authorization())
    asyncio.run(test_security_unregistered_tool_proposed_by_llm_fails_closed())
    asyncio.run(test_security_malformed_json_fails_closed())
    print("ALL P4-3 REAL LLM SECURITY TESTS PASSED SUCCESSFULLY!")
