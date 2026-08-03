"""Observability Correlation Context for Tracing Requests across Subsystems."""
import uuid
from typing import Optional
from dataclasses import dataclass, field

@dataclass
class CorrelationContext:
    """Request correlation context holding trace IDs."""
    correlation_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    workflow_id: Optional[str] = None
    plugin_id: Optional[str] = None
    provider_id: Optional[str] = None

    def to_dict(self) -> dict[str, str]:
        return {
            "correlation_id": self.correlation_id,
            "workflow_id": self.workflow_id or "none",
            "plugin_id": self.plugin_id or "none",
            "provider_id": self.provider_id or "none",
        }
