"""IToolRegistry protocol contract for tool metadata registration, versioning, and capability declaration mapping."""

from __future__ import annotations

from typing import Protocol

from nexusai.brain.domain.governance import ToolCapability
from nexusai.brain.domain.tool_registry import ToolMetadata, ToolStatus


class IToolRegistry(Protocol):
    """Abstract port interface decoupling tool metadata registration from execution and governance engines."""

    async def register(self, metadata: ToolMetadata) -> None:
        """Register a new tool metadata declaration atomically. Rejects duplicate tool_ids."""
        ...

    async def unregister(self, tool_id: str) -> bool:
        """Unregister an active tool metadata entry."""
        ...

    async def get(
        self,
        tool_id: str,
        version: str | None = None,
    ) -> ToolMetadata | None:
        """Retrieve tool metadata by tool_id and optional exact version."""
        ...

    async def list_tools(
        self,
        *,
        status: ToolStatus | None = None,
        capability: ToolCapability | None = None,
    ) -> tuple[ToolMetadata, ...]:
        """List registered tools matching optional status and capability filters."""
        ...

    async def validate_tool(
        self,
        tool_id: str,
        version: str | None = None,
        requested_capabilities: frozenset[ToolCapability] | None = None,
    ) -> ToolMetadata:
        """Validate tool availability, status, exact version, trust policy, and capability escalation bounds."""
        ...
