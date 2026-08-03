"""Unified ToolObserver Layer producing immutable Observation records."""
from typing import Any, Dict, Optional
from nexusai.domain.models import Observation

class ToolObserver:
    """Normalizes raw tool, provider, and permission outputs into unified Observation instances."""

    def create_observation(
        self,
        tool_name: str,
        output_payload: Any,
        source: str = "tool",
        success: bool = True,
        severity: str = "INFO",
    ) -> Observation:
        """Construct a standardized, immutable Observation instance."""
        payload_str = str(output_payload)
        is_success = success and ("Error:" not in payload_str and "Exception" not in payload_str)
        obs_severity = severity if is_success else "ERROR"

        return Observation(
            source=source,
            tool_name=tool_name,
            success=is_success,
            payload=output_payload,
            severity=obs_severity,
        )
