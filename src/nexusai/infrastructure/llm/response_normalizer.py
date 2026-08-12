"""Structured output normalizer and domain schema validator for LLM completion contents."""

from __future__ import annotations

import json
from typing import Any, Mapping

from nexusai.brain.domain.governance import ToolCapability
from nexusai.brain.domain.llm import LLMResponseFormatError
from nexusai.brain.domain.tool_registry import CapabilityEscalationError, ToolMetadata


def validate_structured_plan_output(
    content: str,
    registered_tools: Mapping[str, ToolMetadata] | None = None,
) -> dict[str, Any]:
    """Validate model-generated structured output payload against domain schemas and ToolRegistry bounds."""
    try:
        data = json.loads(content)
    except Exception as err:
        raise LLMResponseFormatError(f"Model completion content is not valid JSON: {err}")

    if not isinstance(data, dict):
        raise LLMResponseFormatError("Structured completion root must be a JSON object")

    if "steps" not in data or not isinstance(data["steps"], list):
        raise LLMResponseFormatError("Structured completion missing required 'steps' list")

    if registered_tools is not None:
        for idx, step in enumerate(data["steps"]):
            if not isinstance(step, dict):
                raise LLMResponseFormatError(f"Step at index {idx} must be a JSON object")

            tool_id = step.get("tool_id")
            if not tool_id or not isinstance(tool_id, str):
                raise LLMResponseFormatError(f"Step at index {idx} missing required string 'tool_id'")

            # P4-3-INV-11: LLM-generated tool identifiers must resolve through ToolRegistry
            if tool_id not in registered_tools:
                raise LLMResponseFormatError(
                    f"LLM proposed tool '{tool_id}' which is not registered in ToolRegistry"
                )

            tool_meta = registered_tools[tool_id]

            # P4-3-INV-10: LLM-generated capabilities CANNOT escalate registered tool capabilities!
            raw_caps = step.get("requested_capabilities", [])
            req_caps = frozenset({ToolCapability(c) for c in raw_caps if c in ToolCapability.__members__ or any(c == tc.value for tc in ToolCapability)})

            if not req_caps.issubset(tool_meta.capabilities):
                raise CapabilityEscalationError(
                    f"Step '{tool_id}' requested capabilities {set(req_caps)} exceeding registered capabilities {set(tool_meta.capabilities)}"
                )

    return data
