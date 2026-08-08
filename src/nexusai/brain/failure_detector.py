"""Two-Layer Failure Pattern Detection for NexusAI Agent Runtime.

Layer 1: FailureEvidence (raw execution failure telemetry)
Layer 2: IFailureClassifier Protocol & RuleFailureClassifier (semantic pattern classification)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class FailureEvidence:
    """Layer 1: Raw evidence collected from tool or step execution failures.

    Attributes:
        tool_name: Executed tool name.
        error_message: Primary error string.
        stderr: Optional standard error output.
        exit_code: Optional process exit code.
        http_status: Optional HTTP status code (e.g. 401, 403, 404, 500, 503).
        is_timeout: Boolean flag indicating wall-clock timeout.
    """

    tool_name: str
    error_message: str
    stderr: str = ""
    exit_code: int | None = None
    http_status: int | None = None
    is_timeout: bool = False


class FailureCategory(str, Enum):
    """Extensible classification categories for runtime failure patterns."""

    NETWORK = "NETWORK"
    PERMISSION = "PERMISSION"
    OSCILLATION = "OSCILLATION"
    CONSECUTIVE_ERROR = "CONSECUTIVE_ERROR"
    VALIDATION = "VALIDATION"
    RESOURCE = "RESOURCE"
    EXECUTION = "EXECUTION"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class FailureAnalysis:
    """Layer 2: Semantic analysis output produced by FailureClassifier.

    Attributes:
        category: High-level FailureCategory classification.
        evidence_items: Tuple of FailureEvidence items supporting analysis.
        recommendation: Actionable natural language self-correction recommendation.
    """

    category: FailureCategory
    evidence_items: tuple[FailureEvidence, ...] = ()
    recommendation: str = ""


@runtime_checkable
class IFailureClassifier(Protocol):
    """Protocol interface for semantic failure pattern classification strategies."""

    def classify(self, evidence_history: list[FailureEvidence]) -> FailureAnalysis | None:
        """Classify failure evidence history into a semantic FailureAnalysis record."""
        ...


class RuleFailureClassifier:
    """Layer 2: Rule-based classifier analyzing FailureEvidence streams into semantic FailureAnalysis."""

    def classify(self, evidence_history: list[FailureEvidence]) -> FailureAnalysis | None:
        """Classify failure evidence history into a semantic FailureAnalysis record."""
        if not evidence_history:
            return None

        recent = evidence_history[-1]
        msg_lower = recent.error_message.lower()

        # 1. Network / Timeout Failure
        if (
            recent.is_timeout
            or (recent.http_status and recent.http_status in {502, 503, 504})
            or any(kw in msg_lower for kw in ["timeout", "connection refused", "network_error"])
        ):
            return FailureAnalysis(
                category=FailureCategory.NETWORK,
                evidence_items=tuple(evidence_history[-3:]),
                recommendation="Transient network error detected. Apply exponential backoff retry.",
            )

        # 2. Permission / Authentication Failure
        if (recent.http_status and recent.http_status in {401, 403}) or any(
            kw in msg_lower
            for kw in ["permission denied", "unauthorized", "access denied", "forbidden"]
        ):
            return FailureAnalysis(
                category=FailureCategory.PERMISSION,
                evidence_items=tuple(evidence_history[-3:]),
                recommendation="Permission or credential issue detected. Request user credential verification.",
            )

        # 3. Tool Oscillation (Ping-Ponging between Tool A and Tool B)
        if len(evidence_history) >= 3:
            tools = [e.tool_name for e in evidence_history[-4:]]
            if len(tools) >= 3 and tools[-1] == tools[-3] and tools[-1] != tools[-2]:
                return FailureAnalysis(
                    category=FailureCategory.OSCILLATION,
                    evidence_items=tuple(evidence_history[-4:]),
                    recommendation=f"Oscillation loop detected between tools '{tools[-1]}' and '{tools[-2]}'. Replan execution strategy.",
                )

        # 4. Consecutive Failures of Same Tool
        if len(evidence_history) >= 2:
            last_two = evidence_history[-2:]
            if last_two[0].tool_name == last_two[1].tool_name:
                return FailureAnalysis(
                    category=FailureCategory.CONSECUTIVE_ERROR,
                    evidence_items=tuple(last_two),
                    recommendation=f"Tool '{recent.tool_name}' failed consecutively. Switch to fallback tool or replan.",
                )

        # Default Execution Error
        return FailureAnalysis(
            category=FailureCategory.EXECUTION,
            evidence_items=(recent,),
            recommendation=f"Execution error on tool '{recent.tool_name}': {recent.error_message}",
        )


# Backward-compatible alias
FailureClassifier = RuleFailureClassifier
