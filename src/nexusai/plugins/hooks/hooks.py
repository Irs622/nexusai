"""
Plugin interceptor hooks definition and payload models.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable


class HookType(str, Enum):
    """Standard OS hook interceptor points."""

    BEFORE_LLM_REQUEST = "before_llm_request"
    AFTER_LLM_REQUEST = "after_llm_request"
    BEFORE_MEMORY_WRITE = "before_memory_write"
    AFTER_MEMORY_WRITE = "after_memory_write"
    BEFORE_TOOL_EXECUTE = "before_tool_execute"
    AFTER_TOOL_EXECUTE = "after_tool_execute"


@dataclass
class HookPayload:
    """Mutable context payload passed through hook execution pipeline."""

    hook_type: HookType
    plugin_id: str
    data: dict[str, Any] = field(default_factory=dict)
    cancelled: bool = False
    cancel_reason: str | None = None


# Async hook handler function signature
HookHandler = Callable[[HookPayload], Awaitable[None]]
