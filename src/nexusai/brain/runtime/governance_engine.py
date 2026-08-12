"""GovernanceEngine runtime implementation enforcing Capability Policies, Execution-Scoped Token Grants, and Atomic Resource Quota Governance."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from nexusai.brain.domain.governance import (
    CapabilityGrant,
    GovernanceDecision,
    GovernanceDenialReason,
    GovernanceRequest,
    ResourceBudget,
    ResourceRequest,
    ResourceReservation,
    ResourceUsage,
    ToolCapability,
)
from nexusai.brain.domain.observability import RuntimeEvent, RuntimeEventType
from nexusai.brain.ports.governance_port import IGovernancePort
from nexusai.brain.ports.observability_port import IObservabilityPort

DEFAULT_TOOL_CAPABILITIES: dict[str, set[ToolCapability]] = {
    "terminal": {ToolCapability.PROCESS_EXEC},
    "file_reader": {ToolCapability.FILE_READ},
    "file_writer": {ToolCapability.FILE_WRITE},
    "http_client": {ToolCapability.NETWORK_ACCESS},
    "system_control": {ToolCapability.SYSTEM_CONTROL},
    "secret_manager": {ToolCapability.SECRET_ACCESS},
}


class GovernanceEngine(IGovernancePort):
    """Deny-by-default capability engine with atomic resource reservations and execution-scoped grant verification."""

    def __init__(
        self,
        global_budget: ResourceBudget | None = None,
        tool_capabilities: dict[str, set[ToolCapability]] | None = None,
        telemetry: IObservabilityPort | None = None,
    ) -> None:
        self.global_budget = global_budget or ResourceBudget(
            max_concurrent_tasks=8,
            max_subprocesses=20,
            max_network_requests=100,
            max_tool_invocations=200,
        )
        self.tool_capabilities = tool_capabilities or dict(DEFAULT_TOOL_CAPABILITIES)
        self.telemetry = telemetry
        self._lock = asyncio.Lock()
        self._active_reservations: dict[str, ResourceReservation] = {}
        self._execution_budgets: dict[str, ResourceBudget] = {}
        self._reservation_counter: int = 0

    def set_execution_budget(self, execution_id: str, budget: ResourceBudget) -> None:
        """Configure execution-scoped resource budget limits."""
        self._execution_budgets[execution_id] = budget

    async def _safe_telemetry_event(
        self,
        event_type: RuntimeEventType,
        exec_id: str,
        node_id: str,
        attributes: dict[str, Any] | None = None,
    ) -> None:
        if not self.telemetry:
            return
        try:
            now = time.time()
            evt = RuntimeEvent(
                event_id=f"gov-evt-{int(now * 1000)}",
                event_type=event_type,
                timestamp=now,
                execution_id=exec_id,
                node_id=node_id,
                attributes=attributes or {},
            )
            await self.telemetry.emit_event(evt)
        except Exception:
            pass

    async def _safe_telemetry_counter(self, name: str, value: int = 1, attributes: dict[str, Any] | None = None) -> None:
        if not self.telemetry:
            return
        try:
            await self.telemetry.increment_counter(name, value, attributes=attributes)
        except Exception:
            pass

    async def authorize(self, request: GovernanceRequest) -> GovernanceDecision:
        """Evaluate capability authorization, grant tokens, and resource quota availability."""
        now = time.time()

        # 1. Negative or malformed resource request validation
        rr = request.resource_request
        if rr.subprocesses < 0 or rr.network_requests < 0 or rr.memory_bytes < 0 or rr.tool_invocations < 0:
            await self._safe_telemetry_event(
                RuntimeEventType.GOVERNANCE_DENIED, request.execution_id, request.node_id,
                attributes={"reason": GovernanceDenialReason.MALFORMED_RESOURCE_REQUEST.value}
            )
            await self._safe_telemetry_counter("nexusai_governance_denials_total")
            return GovernanceDecision(
                allowed=False,
                reason=GovernanceDenialReason.MALFORMED_RESOURCE_REQUEST.value,
                execution_id=request.execution_id,
                node_id=request.node_id,
                tool_name=request.tool_name,
                required_capabilities=request.required_capabilities,
            )

        # 2. Deny-by-default tool capability checking
        declared = self.tool_capabilities.get(request.tool_name)
        if declared is None:
            await self._safe_telemetry_event(
                RuntimeEventType.GOVERNANCE_DENIED, request.execution_id, request.node_id,
                attributes={"reason": GovernanceDenialReason.UNKNOWN_TOOL.value, "tool_name": request.tool_name}
            )
            await self._safe_telemetry_counter("nexusai_governance_denials_total")
            await self._safe_telemetry_counter("nexusai_capability_denials_total")
            return GovernanceDecision(
                allowed=False,
                reason=GovernanceDenialReason.UNKNOWN_TOOL.value,
                execution_id=request.execution_id,
                node_id=request.node_id,
                tool_name=request.tool_name,
                required_capabilities=request.required_capabilities,
            )

        if not request.required_capabilities.issubset(declared):
            await self._safe_telemetry_event(
                RuntimeEventType.CAPABILITY_DENIED, request.execution_id, request.node_id,
                attributes={"reason": GovernanceDenialReason.CAPABILITY_MISSING.value, "tool_name": request.tool_name}
            )
            await self._safe_telemetry_counter("nexusai_governance_denials_total")
            await self._safe_telemetry_counter("nexusai_capability_denials_total")
            return GovernanceDecision(
                allowed=False,
                reason=GovernanceDenialReason.CAPABILITY_MISSING.value,
                execution_id=request.execution_id,
                node_id=request.node_id,
                tool_name=request.tool_name,
                required_capabilities=request.required_capabilities,
            )

        # 3. Execution-scoped grant token validation
        if request.grant is not None:
            if request.grant.execution_id != request.execution_id:
                await self._safe_telemetry_event(
                    RuntimeEventType.GOVERNANCE_DENIED, request.execution_id, request.node_id,
                    attributes={"reason": GovernanceDenialReason.GRANT_EXECUTION_MISMATCH.value}
                )
                await self._safe_telemetry_counter("nexusai_governance_denials_total")
                await self._safe_telemetry_counter("nexusai_capability_denials_total")
                return GovernanceDecision(
                    allowed=False,
                    reason=GovernanceDenialReason.GRANT_EXECUTION_MISMATCH.value,
                    execution_id=request.execution_id,
                    node_id=request.node_id,
                    tool_name=request.tool_name,
                    required_capabilities=request.required_capabilities,
                )

            if request.grant.expires_at is not None and now > request.grant.expires_at:
                await self._safe_telemetry_event(
                    RuntimeEventType.GOVERNANCE_DENIED, request.execution_id, request.node_id,
                    attributes={"reason": GovernanceDenialReason.GRANT_EXPIRED.value}
                )
                await self._safe_telemetry_counter("nexusai_governance_denials_total")
                await self._safe_telemetry_counter("nexusai_capability_denials_total")
                return GovernanceDecision(
                    allowed=False,
                    reason=GovernanceDenialReason.GRANT_EXPIRED.value,
                    execution_id=request.execution_id,
                    node_id=request.node_id,
                    tool_name=request.tool_name,
                    required_capabilities=request.required_capabilities,
                )

            if not request.required_capabilities.issubset(request.grant.granted_capabilities):
                await self._safe_telemetry_event(
                    RuntimeEventType.CAPABILITY_DENIED, request.execution_id, request.node_id,
                    attributes={"reason": GovernanceDenialReason.CAPABILITY_MISSING.value}
                )
                await self._safe_telemetry_counter("nexusai_governance_denials_total")
                await self._safe_telemetry_counter("nexusai_capability_denials_total")
                return GovernanceDecision(
                    allowed=False,
                    reason=GovernanceDenialReason.CAPABILITY_MISSING.value,
                    execution_id=request.execution_id,
                    node_id=request.node_id,
                    tool_name=request.tool_name,
                    required_capabilities=request.required_capabilities,
                )

        # 4. Atomic Resource Quota Check
        reservation = await self.reserve(request.execution_id, request.node_id, request.resource_request)
        if reservation is None:
            await self._safe_telemetry_event(
                RuntimeEventType.GOVERNANCE_DENIED, request.execution_id, request.node_id,
                attributes={"reason": GovernanceDenialReason.RESOURCE_QUOTA_EXCEEDED.value}
            )
            await self._safe_telemetry_counter("nexusai_governance_denials_total")
            await self._safe_telemetry_counter("nexusai_resource_quota_exhaustions_total")
            return GovernanceDecision(
                allowed=False,
                reason=GovernanceDenialReason.RESOURCE_QUOTA_EXCEEDED.value,
                execution_id=request.execution_id,
                node_id=request.node_id,
                tool_name=request.tool_name,
                required_capabilities=request.required_capabilities,
            )

        await self._safe_telemetry_event(
            RuntimeEventType.GOVERNANCE_AUTHORIZED, request.execution_id, request.node_id,
            attributes={"tool_name": request.tool_name}
        )
        await self._safe_telemetry_counter("nexusai_governance_authorizations_total")

        granted_caps = request.grant.granted_capabilities if request.grant else frozenset(declared)
        return GovernanceDecision(
            allowed=True,
            reason="AUTHORIZED",
            execution_id=request.execution_id,
            node_id=request.node_id,
            tool_name=request.tool_name,
            required_capabilities=request.required_capabilities,
            granted_capabilities=granted_caps,
            reservation_id=reservation.reservation_id,
        )

    async def reserve(
        self,
        execution_id: str,
        node_id: str,
        request: ResourceRequest,
    ) -> ResourceReservation | None:
        """Atomically reserve resources prior to execution. Returns None if quota exceeded."""
        async with self._lock:
            # Calculate active global usage
            curr_subproc = sum(r.subprocesses for r in self._active_reservations.values())
            curr_netreq = sum(r.network_requests for r in self._active_reservations.values())
            curr_mem = sum(r.memory_bytes for r in self._active_reservations.values())
            curr_invoc = sum(r.tool_invocations for r in self._active_reservations.values())

            # Calculate active execution usage
            exec_reservations = [r for r in self._active_reservations.values() if r.execution_id == execution_id]
            curr_exec_subproc = sum(r.subprocesses for r in exec_reservations)
            curr_exec_netreq = sum(r.network_requests for r in exec_reservations)
            curr_exec_mem = sum(r.memory_bytes for r in exec_reservations)
            curr_exec_invoc = sum(r.tool_invocations for r in exec_reservations)

            exec_budget = self._execution_budgets.get(execution_id, self.global_budget)

            # Atomic All-or-Nothing check against global AND execution budgets
            if (curr_subproc + request.subprocesses > self.global_budget.max_subprocesses or
                curr_netreq + request.network_requests > self.global_budget.max_network_requests or
                curr_mem + request.memory_bytes > self.global_budget.max_memory_bytes or
                curr_invoc + request.tool_invocations > self.global_budget.max_tool_invocations or
                curr_exec_subproc + request.subprocesses > exec_budget.max_subprocesses or
                curr_exec_netreq + request.network_requests > exec_budget.max_network_requests or
                curr_exec_mem + request.memory_bytes > exec_budget.max_memory_bytes or
                curr_exec_invoc + request.tool_invocations > exec_budget.max_tool_invocations):
                
                if self.telemetry:
                    try:
                        await self.telemetry.increment_counter("nexusai_resource_reservation_failures_total")
                    except Exception:
                        pass
                return None

            # All checks passed: atomically create reservation
            self._reservation_counter += 1
            res_id = f"res-{execution_id}-{node_id}-{self._reservation_counter}"

            reservation = ResourceReservation(
                reservation_id=res_id,
                execution_id=execution_id,
                node_id=node_id,
                subprocesses=request.subprocesses,
                network_requests=request.network_requests,
                memory_bytes=request.memory_bytes,
                tool_invocations=request.tool_invocations,
            )
            self._active_reservations[res_id] = reservation

        if self.telemetry:
            try:
                await self.telemetry.emit_event(
                    RuntimeEvent(
                        event_id=f"gov-res-{res_id}",
                        event_type=RuntimeEventType.RESOURCE_RESERVED,
                        execution_id=execution_id,
                        node_id=node_id,
                    )
                )
                await self.telemetry.increment_counter("nexusai_resource_reservations_total")
            except Exception:
                pass

        return reservation

    async def release(self, reservation_id: str) -> bool:
        """Release an active resource reservation across all execution termination paths."""
        async with self._lock:
            reservation = self._active_reservations.pop(reservation_id, None)

        if reservation and self.telemetry:
            try:
                await self.telemetry.emit_event(
                    RuntimeEvent(
                        event_id=f"gov-rel-{reservation_id}",
                        event_type=RuntimeEventType.RESOURCE_RELEASED,
                        execution_id=reservation.execution_id,
                        node_id=reservation.node_id,
                    )
                )
            except Exception:
                pass

        return reservation is not None

    async def record_usage(self, reservation_id: str, usage: ResourceUsage) -> None:
        """Record actual resources consumed during execution prior to release."""
        if self.telemetry:
            try:
                await self.telemetry.increment_counter(
                    "nexusai_resource_usage_total",
                    value=usage.tool_invocations_used,
                )
            except Exception:
                pass

    def get_active_reservation_count(self) -> int:
        """Return count of currently active resource reservations."""
        return len(self._active_reservations)
