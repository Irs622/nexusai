"""Health readiness and liveness probes incorporating disaster recovery quarantine state checks."""

from __future__ import annotations

from typing import Any

from nexusai.brain.domain.recovery import RecoveryStatus
from nexusai.brain.ports.observability_port import IObservabilityHealth


class ObservabilityHealthService(IObservabilityHealth):
    """Health readiness and liveness probe service."""

    def __init__(self, current_recovery_status: RecoveryStatus = RecoveryStatus.READY) -> None:
        self.current_recovery_status = current_recovery_status
        self.dependencies_ok: bool = True

    def is_alive(self) -> bool:
        """Process liveness probe."""
        return True

    def is_ready(self) -> bool:
        """Process readiness probe (returns False if recovery state is QUARANTINED or FAILED)."""
        if self.current_recovery_status in (RecoveryStatus.QUARANTINED, RecoveryStatus.FAILED):
            return False
        return self.dependencies_ok
