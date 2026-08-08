"""
MemoryService application facade entrypoint inheriting from KernelService and delegating to specialized sub-services.
"""

from __future__ import annotations

from typing import Any

from nexusai.kernel.service import KernelService, ServiceDescriptor, ServiceLifecycleState
from nexusai.memory.contracts.retrieval import QueryResult
from nexusai.memory.domain.metadata import MemoryMetadata
from nexusai.memory.domain.record import MemoryRecord, MemoryScope, MemoryType
from nexusai.memory.services.admin import MemoryAdminService
from nexusai.memory.services.command import MemoryCommandService
from nexusai.memory.services.query import MemoryQueryService


class MemoryService(KernelService):
    """MemoryService public facade entrypoint delegating to specialized MemoryCommandService, MemoryQueryService, and MemoryAdminService."""

    def __init__(
        self,
        command_service: MemoryCommandService,
        query_service: MemoryQueryService,
        admin_service: MemoryAdminService,
        descriptor: ServiceDescriptor | None = None,
    ) -> None:
        desc = descriptor or ServiceDescriptor(
            id="memory_service",
            name="NexusAI Memory Engine Service",
            version="2.4.12",
        )
        super().__init__(desc)
        self._command = command_service
        self._query = query_service
        self._admin = admin_service

    def set_degraded_status(self, degraded: bool) -> None:
        """Set degraded health status."""
        self._admin.set_degraded_status(degraded)

    async def initialize(self) -> None:
        """Initialize MemoryService."""
        self._state = ServiceLifecycleState.INITIALIZED

    async def start(self) -> None:
        """Start MemoryService."""
        self._state = ServiceLifecycleState.RUNNING

    async def stop(self) -> None:
        """Stop MemoryService."""
        self._state = ServiceLifecycleState.STOPPED

    async def shutdown(self) -> None:
        """Shutdown MemoryService."""
        await self.stop()

    async def health(self) -> dict[str, Any]:
        """Return rich diagnostic subsystem health check probes."""
        res = await self._admin.health(self.state)
        res["service_id"] = self.descriptor.id
        return res

    async def metrics(self) -> dict[str, Any]:
        """Return operational telemetry metrics summary."""
        return self._admin.metrics()

    async def store(
        self,
        raw_text: str,
        memory_type: MemoryType = MemoryType.EPISODIC,
        scope: MemoryScope = MemoryScope.SESSION,
        metadata: MemoryMetadata | None = None,
    ) -> MemoryRecord:
        """Store MemoryRecord via MemoryCommandService."""
        return await self._command.store(
            raw_text=raw_text, memory_type=memory_type, scope=scope, metadata=metadata
        )

    async def retrieve(self, record_id: str) -> MemoryRecord | None:
        """Retrieve MemoryRecord via MemoryQueryService."""
        return await self._query.retrieve(record_id=record_id)

    async def search(
        self,
        query: str,
        top_k: int = 5,
        metadata_filters: dict[str, Any] | None = None,
    ) -> QueryResult:
        """Search MemoryRecord via MemoryQueryService."""
        return await self._query.search(query=query, top_k=top_k, metadata_filters=metadata_filters)

    async def forget(self, record_id: str) -> bool:
        """Forget MemoryRecord via MemoryCommandService."""
        return await self._command.forget(record_id=record_id)

    async def archive(self, record_id: str, reason: str = "user_action") -> bool:
        """Archive MemoryRecord via MemoryCommandService."""
        return await self._command.archive(record_id=record_id, reason=reason)

    async def vacuum(self) -> bool:
        """Execute storage vacuum via MemoryAdminService."""
        return await self._admin.vacuum()

    async def reindex(self) -> bool:
        """Execute vector reindex via MemoryAdminService."""
        return await self._admin.reindex()
