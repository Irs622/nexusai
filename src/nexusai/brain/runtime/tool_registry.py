"""ToolRegistry runtime implementation providing atomic tool registration, semver validation, capability escalation protection, and trust policies."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from nexusai.brain.domain.governance import ToolCapability
from nexusai.brain.domain.observability import RuntimeEvent, RuntimeEventType
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
from nexusai.brain.ports.observability_port import IObservabilityPort
from nexusai.brain.ports.tool_registry_port import IToolRegistry


class ToolRegistry(IToolRegistry):
    """Thread and coroutine safe ToolRegistry enforcing unique tool IDs, status checks, SemVer matching, capability escalation prevention, and trust policies."""

    def __init__(
        self,
        telemetry: IObservabilityPort | None = None,
    ) -> None:
        self.telemetry = telemetry
        self._lock = asyncio.Lock()
        self._tools: dict[str, ToolMetadata] = {}

    async def _safe_telemetry_event(
        self,
        event_type: RuntimeEventType,
        tool_id: str,
        attributes: dict[str, Any] | None = None,
    ) -> None:
        if not self.telemetry:
            return
        try:
            now = time.time()
            evt = RuntimeEvent(
                event_id=f"reg-evt-{tool_id}-{int(now * 1000)}",
                event_type=event_type,
                timestamp=now,
                attributes={"tool_id": tool_id, **(attributes or {})},
            )
            await self.telemetry.emit_event(evt)
        except Exception:
            pass

    async def register(self, metadata: ToolMetadata) -> None:
        """Register a new tool metadata declaration atomically. Rejects duplicate tool_ids."""
        async with self._lock:
            if metadata.tool_id in self._tools:
                raise ToolAlreadyRegisteredError(
                    f"Tool '{metadata.tool_id}' is already registered in registry"
                )
            self._tools[metadata.tool_id] = metadata

        await self._safe_telemetry_event(
            RuntimeEventType.TOOL_STARTED,  # Reusing semantic registration telemetry
            tool_id=metadata.tool_id,
            attributes={"version": metadata.version, "trust_level": metadata.trust_level.value},
        )

    async def unregister(self, tool_id: str) -> bool:
        """Unregister an active tool metadata entry."""
        async with self._lock:
            removed = self._tools.pop(tool_id, None)

        if removed:
            await self._safe_telemetry_event(
                RuntimeEventType.TOOL_CANCELLED,
                tool_id=tool_id,
            )

        return removed is not None

    async def get(
        self,
        tool_id: str,
        version: str | None = None,
    ) -> ToolMetadata | None:
        """Retrieve tool metadata by tool_id and optional exact version."""
        async with self._lock:
            meta = self._tools.get(tool_id)
            if meta is None:
                return None
            if version is not None and meta.version != version:
                return None
            return meta

    async def list_tools(
        self,
        *,
        status: ToolStatus | None = None,
        capability: ToolCapability | None = None,
    ) -> tuple[ToolMetadata, ...]:
        """List registered tools matching optional status and capability filters."""
        async with self._lock:
            all_metas = list(self._tools.values())

        filtered: list[ToolMetadata] = []
        for meta in all_metas:
            # Default filter excludes DISABLED and REVOKED tools unless status is explicitly asked
            if status is not None:
                if meta.status != status:
                    continue
            else:
                if meta.status in (ToolStatus.DISABLED, ToolStatus.REVOKED):
                    continue

            if capability is not None:
                if capability not in meta.capabilities:
                    continue

            filtered.append(meta)

        # Deterministic ordering by tool_id ASC
        filtered.sort(key=lambda m: m.tool_id)
        return tuple(filtered)

    async def validate_tool(
        self,
        tool_id: str,
        version: str | None = None,
        requested_capabilities: frozenset[ToolCapability] | None = None,
    ) -> ToolMetadata:
        """Validate tool availability, status, exact version, trust policy, and capability escalation bounds."""
        async with self._lock:
            meta = self._tools.get(tool_id)

        if meta is None:
            raise ValueError(f"Tool '{tool_id}' not found in registry")

        # P3-2-INV-02: Disabled or Revoked tools cannot execute
        if meta.status in (ToolStatus.DISABLED, ToolStatus.REVOKED):
            raise ToolUnavailableError(
                f"Tool '{tool_id}' is unavailable for execution (status: {meta.status.value})"
            )

        # Exact semver matching check
        if version is not None and meta.version != version:
            raise ToolVersionMismatchError(
                f"Tool '{tool_id}' version mismatch: requested '{version}', registered '{meta.version}'"
            )

        # Trust policy check: UNTRUSTED tools denied by default
        if meta.trust_level == ToolTrustLevel.UNTRUSTED:
            raise TrustPolicyError(
                f"Tool '{tool_id}' is UNTRUSTED and denied by default trust policy"
            )

        # Capability escalation check
        if requested_capabilities is not None:
            validate_declared_capabilities(meta, requested_capabilities)

        return meta
