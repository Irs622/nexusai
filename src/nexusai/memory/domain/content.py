"""
MemoryContent domain value object.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class MemoryContent(BaseModel):
    """Heavy content text payload and summary container."""

    raw_text: str = Field(..., description="Full raw text content")
    summary: str | None = Field(default=None, description="Compacted text summary if processed")
    embedding_id: str | None = Field(
        default=None, description="Reference ID of vector embedding in VectorStore"
    )

    model_config = {
        "frozen": True,
        "arbitrary_types_allowed": True,
    }
