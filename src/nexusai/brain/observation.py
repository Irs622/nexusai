"""Unified ObservationMapper and ToolObserver layer producing immutable Observation records."""

from __future__ import annotations

from typing import Any

from nexusai.brain.ports.tool_port import ToolExecutionResult
from nexusai.domain.models import Observation


class ObservationMapper:
    """Transforms ToolExecutionResult instances into tool-agnostic Observation domain entities."""

    def map_tool_result(self, result: ToolExecutionResult) -> Observation:
        """Map ToolExecutionResult to a standardized Observation record.

        Args:
            result: ToolExecutionResult output from IToolPort.

        Returns:
            Normalized Observation domain entity.
        """
        payload = (
            getattr(result, "result", None)
            or getattr(result, "output", None)
            or (result.error_message if not result.success else "Success")
        )
        severity = "INFO" if result.success else "ERROR"

        return Observation(
            source="tool",
            tool_name=result.tool_name,
            success=result.success,
            payload=payload,
            severity=severity,
            metrics={"execution_time_ms": result.execution_time_ms},
        )


class ToolObserver:
    """ToolObserver layer producing immutable Observation records from tool execution output."""

    def __init__(self, mapper: ObservationMapper | None = None) -> None:
        self._mapper = mapper or ObservationMapper()

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

    def map_result(self, result: ToolExecutionResult) -> Observation:
        """Delegate tool result normalization to ObservationMapper."""
        return self._mapper.map_tool_result(result)
