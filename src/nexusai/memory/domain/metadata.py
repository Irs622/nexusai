"""
MemoryMetadata domain value object.
"""

from __future__ import annotations

import time
from typing import Any

from pydantic import BaseModel, Field


class MemoryMetadata(BaseModel):
    """Metadata container for MemoryRecords."""

    importance: float = Field(default=0.5, description="Importance score from 0.0 to 1.0")
    tags: list[str] = Field(default_factory=list, description="Categorical tags")
    ttl_seconds: float | None = Field(
        default=None, description="Time-To-Live in seconds if temporary"
    )
    source: str = Field(default="user", description="Memory origin (user, system, agent, tool)")
    owner: str = Field(default="default", description="Memory owner or session ID")
    created_at: float = Field(default_factory=time.time, description="Creation epoch timestamp")
    updated_at: float = Field(default_factory=time.time, description="Last update epoch timestamp")
    archived: bool = Field(default=False, description="True if memory record is archived")
    custom: dict[str, Any] = Field(default_factory=dict, description="Arbitrary key-value metadata")

    model_config = {
        "frozen": True,
        "arbitrary_types_allowed": True,
    }
