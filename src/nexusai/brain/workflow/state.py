"""
TypedDict State schema for LangGraph Agentic Workflow.
"""

from __future__ import annotations

from typing import Any, Optional, TypedDict


class NexusGraphState(TypedDict):
    """Graph state tracking session context, messages, iterations, and tool call intentions."""

    session_id: str
    messages: list[dict[str, Any]]
    tools: Optional[list[dict[str, Any]]]
    final_response: Optional[str]
    iterations: int
    user_confirmed: bool
    max_iterations: int
    last_tool_call: Optional[dict[str, Any]]
