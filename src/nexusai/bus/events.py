"""
Domain Events definition for Pub/Sub EventBus.
"""

from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field


class ToolExecutedEvent(BaseModel):
    """Event emitted whenever a tool execution finishes."""

    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    result: Any = None
    success: bool = True
    error: str | None = None
