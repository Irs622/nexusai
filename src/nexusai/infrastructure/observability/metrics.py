"""Prometheus-compatible metric recorder with strict label allowlists and cardinality bounds."""

from __future__ import annotations

from typing import Any, Mapping

from nexusai.brain.ports.observability_port import IMetricRecorder


class HighCardinalityLabelViolation(Exception):
    """Raised when high-cardinality labels (execution_id, prompt, session_id) are passed to metric labels."""


class PrometheusMetricRecorder(IMetricRecorder):
    """Production-grade metric recorder enforcing strict label allowlists to prevent Prometheus label cardinality explosion."""

    ALLOWED_LABELS = {
        "tool_id",
        "provider",
        "operation",
        "status",
        "risk_level",
        "sandbox_result",
        "error_type",
        "recovery_status",
    }

    FORBIDDEN_LABELS = {
        "execution_id",
        "session_id",
        "user_id",
        "request_id",
        "prompt",
        "completion",
        "url",
        "path",
        "credential_ref",
        "exception",
    }

    def __init__(self) -> None:
        self.counters: dict[str, float] = {}
        self.histograms: dict[str, list[float]] = {}
        self.gauges: dict[str, float] = {}

    def _validate_labels(self, labels: Mapping[str, str] | None) -> None:
        if not labels:
            return
        for key in labels.keys():
            if key in self.FORBIDDEN_LABELS or key not in self.ALLOWED_LABELS:
                raise HighCardinalityLabelViolation(
                    f"Label '{key}' is FORBIDDEN in metric attributes due to high-cardinality explosion risks!"
                )

    def increment_counter(self, name: str, value: float = 1.0, labels: Mapping[str, str] | None = None) -> None:
        self._validate_labels(labels)
        self.counters[name] = self.counters.get(name, 0.0) + value

    def record_histogram(self, name: str, value: float, labels: Mapping[str, str] | None = None) -> None:
        self._validate_labels(labels)
        if name not in self.histograms:
            self.histograms[name] = []
        self.histograms[name].append(value)

    def set_gauge(self, name: str, value: float, labels: Mapping[str, str] | None = None) -> None:
        self._validate_labels(labels)
        self.gauges[name] = value
