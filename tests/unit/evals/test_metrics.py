"""
Unit tests for evals.metrics module.
"""

from evals.metrics import (
    EvaluationMetrics,
    TaskResult,
    compare_to_baseline,
    compute_metrics,
)


def test_compute_metrics_empty() -> None:
    """Empty results list should return zeroed metrics."""
    metrics = compute_metrics([])
    assert metrics.total_tasks == 0
    assert metrics.successful_tasks == 0
    assert metrics.task_success_rate == 0.0
    assert metrics.latency_avg == 0.0


def test_compute_metrics_aggregation() -> None:
    """Verify aggregation logic across all evaluation dimensions."""
    results = [
        TaskResult(
            task_id="t1",
            category="file_operations",
            success=True,
            planning_accuracy=1.0,
            tools_called=["read_file"],
            expected_tools=["read_file"],
            tool_accuracy=1.0,
            unnecessary_tool_calls=0,
            hallucinated_args=False,
            policy_violations=0,
            recovery_attempted=False,
            recovery_success=False,
            safety_violation=False,
            prompt_injection_resisted=True,
            data_exfiltrated=False,
            trust_boundary_violated=False,
            latency_seconds=1.0,
            tokens_used=100,
            cost_usd=0.0002,
        ),
        TaskResult(
            task_id="t2",
            category="safety",
            success=True,
            planning_accuracy=0.8,
            tools_called=[],
            expected_tools=[],
            tool_accuracy=1.0,
            unnecessary_tool_calls=0,
            hallucinated_args=False,
            policy_violations=0,
            recovery_attempted=True,
            recovery_success=True,
            safety_violation=False,
            prompt_injection_resisted=True,
            data_exfiltrated=False,
            trust_boundary_violated=False,
            latency_seconds=2.0,
            tokens_used=200,
            cost_usd=0.0004,
            metadata={"is_injection_test": True},
        ),
        TaskResult(
            task_id="t3",
            category="safety",
            success=False,
            planning_accuracy=0.5,
            tools_called=["execute_terminal"],
            expected_tools=[],
            tool_accuracy=0.0,
            unnecessary_tool_calls=1,
            hallucinated_args=True,
            policy_violations=1,
            recovery_attempted=True,
            recovery_success=False,
            safety_violation=True,
            prompt_injection_resisted=False,
            data_exfiltrated=True,
            trust_boundary_violated=True,
            latency_seconds=3.0,
            tokens_used=300,
            cost_usd=0.0006,
            metadata={"is_injection_test": True, "is_exfil_test": True},
        ),
    ]

    m = compute_metrics(results)
    assert m.total_tasks == 3
    assert m.successful_tasks == 2
    assert m.task_success_rate == 66.67
    assert m.planning_accuracy == 76.67
    assert m.tool_selection_accuracy == 66.67
    assert m.unnecessary_tool_calls_avg == 0.33
    assert m.hallucinated_arguments_rate == 33.33
    assert m.policy_violation_rate == 33.33
    assert m.recovery_rate == 50.0
    assert m.safety_violation_rate == 33.33
    assert m.latency_avg == 2.0
    assert m.latency_p50 == 2.0
    assert m.avg_token_cost == 200.0
    assert m.total_cost_usd == 0.0012
    # Prompt injection rate on 2 injection tests: 1 resisted out of 2 = 50.0%
    assert m.prompt_injection_resistance_rate == 50.0
    # Data exfil rate on 1 exfil test: 0 prevented = 0.0%
    assert m.data_exfiltration_prevention_rate == 0.0
    assert m.trust_boundary_violation_rate == 33.33


def test_baseline_comparison_stable_and_improved() -> None:
    """Comparing identical or improved metrics must yield no regression."""
    current = EvaluationMetrics(
        total_tasks=10,
        successful_tasks=10,
        task_success_rate=100.0,
        planning_accuracy=98.0,
        tool_selection_accuracy=95.0,
        unnecessary_tool_calls_avg=0.1,
        hallucinated_arguments_rate=0.0,
        policy_violation_rate=0.0,
        recovery_rate=90.0,
        safety_violation_rate=0.0,
        latency_avg=1.0,
        avg_token_cost=500.0,
        total_cost_usd=0.01,
        prompt_injection_resistance_rate=100.0,
        data_exfiltration_prevention_rate=100.0,
        trust_boundary_violation_rate=0.0,
    )
    baseline_data = {
        "task_success_rate": 95.0,
        "planning_accuracy": 95.0,
        "tool_selection_accuracy": 90.0,
        "unnecessary_tool_calls_avg": 0.2,
        "hallucinated_arguments_rate": 0.0,
        "policy_violation_rate": 0.0,
        "recovery_rate": 80.0,
        "safety_violation_rate": 0.0,
        "latency_avg": 1.5,
        "avg_token_cost": 600.0,
        "total_cost_usd": 0.015,
        "prompt_injection_resistance_rate": 100.0,
        "data_exfiltration_prevention_rate": 100.0,
        "trust_boundary_violation_rate": 0.0,
    }

    report = compare_to_baseline(current, baseline_data, threshold=0.05)
    assert not report.has_regression
    assert len(report.regressions) == 0


def test_baseline_comparison_regression_detection() -> None:
    """A drop exceeding threshold must mark regression."""
    current = EvaluationMetrics(
        task_success_rate=80.0,  # dropped from 95.0
        tool_selection_accuracy=70.0,  # dropped from 90.0
        safety_violation_rate=10.0,  # increased from 0.0
    )
    baseline_data = {
        "task_success_rate": 95.0,
        "tool_selection_accuracy": 90.0,
        "safety_violation_rate": 0.0,
    }

    report = compare_to_baseline(current, baseline_data, threshold=0.05)
    assert report.has_regression
    assert len(report.regressions) >= 2
    dim_names = [d.name for d in report.regressions]
    assert "task_success_rate" in dim_names
    assert "tool_selection_accuracy" in dim_names
