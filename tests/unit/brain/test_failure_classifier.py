"""Unit tests for Two-Layer Failure Pattern Detector (FailureEvidence & FailureClassifier)."""

from nexusai.brain.failure_detector import (
    FailureCategory,
    FailureClassifier,
    FailureEvidence,
)


def test_network_failure_classification():
    """Verify classification of timeout and network errors."""
    classifier = FailureClassifier()
    ev = FailureEvidence(tool_name="web_fetch", error_message="Connection timeout", is_timeout=True)
    analysis = classifier.classify([ev])

    assert analysis is not None
    assert analysis.category == FailureCategory.NETWORK
    assert "backoff retry" in analysis.recommendation


def test_permission_failure_classification():
    """Verify classification of permission denied errors."""
    classifier = FailureClassifier()
    ev = FailureEvidence(
        tool_name="workspace_write", error_message="Permission denied: /etc/hosts", http_status=403
    )
    analysis = classifier.classify([ev])

    assert analysis is not None
    assert analysis.category == FailureCategory.PERMISSION
    assert (
        "credential" in analysis.recommendation.lower()
        or "permission" in analysis.recommendation.lower()
    )


def test_oscillation_failure_classification():
    """Verify classification of tool oscillation loops (Tool A -> Tool B -> Tool A)."""
    classifier = FailureClassifier()
    ev1 = FailureEvidence(tool_name="tool_a", error_message="err 1")
    ev2 = FailureEvidence(tool_name="tool_b", error_message="err 2")
    ev3 = FailureEvidence(tool_name="tool_a", error_message="err 3")

    analysis = classifier.classify([ev1, ev2, ev3])

    assert analysis is not None
    assert analysis.category == FailureCategory.OSCILLATION
    assert "Oscillation" in analysis.recommendation


def test_consecutive_failure_classification():
    """Verify classification of consecutive tool errors."""
    classifier = FailureClassifier()
    ev1 = FailureEvidence(tool_name="tool_a", error_message="err 1")
    ev2 = FailureEvidence(tool_name="tool_a", error_message="err 2")

    analysis = classifier.classify([ev1, ev2])

    assert analysis is not None
    assert analysis.category == FailureCategory.CONSECUTIVE_ERROR
    assert "consecutively" in analysis.recommendation
