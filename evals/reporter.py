"""Reporter module for formatting human-readable and structured evaluation reports."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from evals.metrics import DimensionComparison, DimensionStatus, EvaluationMetrics, RegressionReport, TaskResult


def _format_dim_title(name: str) -> str:
    """Format dimension key into friendly display title."""
    mapping = {
        "task_success_rate": "Task Success",
        "planning_accuracy": "Planning Accuracy",
        "tool_selection_accuracy": "Tool Accuracy",
        "unnecessary_tool_calls_avg": "Unnecessary Calls",
        "hallucinated_arguments_rate": "Hallucinated Args",
        "policy_violation_rate": "Policy Violations",
        "recovery_rate": "Recovery Rate",
        "safety_violation_rate": "Safety Violations",
        "latency_avg": "Avg Latency",
        "avg_token_cost": "Avg Token Cost",
        "total_cost_usd": "Total Cost USD",
        "prompt_injection_resistance_rate": "Prompt Injection Resistance",
        "data_exfiltration_prevention_rate": "Data Exfiltration Prevention",
        "trust_boundary_violation_rate": "Trust Boundary Violations",
    }
    return mapping.get(name, name.replace("_", " ").title())


def _format_value(value: float, unit: str) -> str:
    """Format numerical value with its associated unit."""
    if unit == "%":
        return f"{value:.1f}%"
    if unit == "s":
        return f"{value:.2f}s"
    if unit == "tokens":
        return f"{int(value):,}"
    if unit == "calls":
        return f"{value:.2f}"
    if unit == "$":
        return f"${value:.4f}"
    return f"{value:.2f}"



def format_terminal_report(
    metrics: EvaluationMetrics,
    regression: RegressionReport | None = None,
) -> str:
    """Format human-readable evaluation summary for terminal display.

    Args:
        metrics: Aggregated run metrics.
        regression: Optional regression report against baseline.

    Returns:
        Formatted multi-line string for terminal output.
    """
    lines: list[str] = []
    lines.append("================================================================================")
    lines.append("                 NEXUSAI AGENT RUNTIME EVALUATION REPORT                        ")
    lines.append("================================================================================")
    lines.append(f"Evaluated Tasks: {metrics.total_tasks} | Succeeded: {metrics.successful_tasks}")
    lines.append("--------------------------------------------------------------------------------")

    if regression is not None:
        lines.append("DIMENSION                   CURRENT        BASELINE       STATUS")
        lines.append("--------------------------------------------------------------------------------")
        for dim, comp in regression.comparisons.items():
            title = _format_dim_title(dim).ljust(26)
            curr_str = _format_value(comp.current_value, comp.unit).ljust(14)
            base_str = _format_value(comp.baseline_value, comp.unit).ljust(14)

            if comp.status == DimensionStatus.IMPROVED:
                status_str = f"✓ IMPROVED ({comp.delta:+.1f}{comp.unit})"
            elif comp.status == DimensionStatus.REGRESSION:
                status_str = f"⚠ REGRESSION ({comp.delta:+.1f}{comp.unit})"
            else:
                status_str = "✓ STABLE"

            lines.append(f"{title} {curr_str} {base_str} {status_str}")

        lines.append("--------------------------------------------------------------------------------")
        if regression.has_regression:
            lines.append(
                f"[STATUS] ❌ REGRESSION DETECTED: {regression.regression_count} dimension(s) dropped beyond {int(regression.threshold * 100)}% threshold."
            )
        else:
            lines.append(
                f"[STATUS] ✅ PASSED: All {len(regression.comparisons)} dimensions met or exceeded baseline targets."
            )
    else:
        lines.append("DIMENSION                   MEASUREMENT")
        lines.append("--------------------------------------------------------------------------------")
        lines.append(f"{'Task Success Rate'.ljust(26)} {metrics.task_success_rate:.1f}% ({metrics.successful_tasks}/{metrics.total_tasks})")
        lines.append(f"{'Planning Accuracy'.ljust(26)} {metrics.planning_accuracy:.1f}%")
        lines.append(f"{'Tool Selection Accuracy'.ljust(26)} {metrics.tool_selection_accuracy:.1f}%")
        lines.append(f"{'Unnecessary Tool Calls'.ljust(26)} {metrics.unnecessary_tool_calls_avg:.2f} avg")
        lines.append(f"{'Hallucinated Args Rate'.ljust(26)} {metrics.hallucinated_arguments_rate:.1f}%")
        lines.append(f"{'Policy Violation Rate'.ljust(26)} {metrics.policy_violation_rate:.1f}%")
        lines.append(f"{'Recovery Rate'.ljust(26)} {metrics.recovery_rate:.1f}%")
        lines.append(f"{'Avg Latency'.ljust(26)} {metrics.latency_avg:.2f}s (p50: {metrics.latency_p50:.2f}s, p95: {metrics.latency_p95:.2f}s, p99: {metrics.latency_p99:.2f}s)")
        lines.append(f"{'Avg Token Cost'.ljust(26)} {int(metrics.avg_token_cost):,} tokens")
        lines.append(f"{'Total Cost USD'.ljust(26)} ${metrics.total_cost_usd:.4f}")
        lines.append(f"{'Prompt Injection Resisted'.ljust(26)} {metrics.prompt_injection_resistance_rate:.1f}%")
        lines.append(f"{'Data Exfiltration Blocked'.ljust(26)} {metrics.data_exfiltration_prevention_rate:.1f}%")
        lines.append(f"{'Trust Boundary Violations'.ljust(26)} {metrics.trust_boundary_violation_rate:.1f}%")
        lines.append("--------------------------------------------------------------------------------")
        lines.append("[STATUS] ✅ Evaluation run completed successfully.")

    lines.append("================================================================================")
    return "\n".join(lines)


def format_json_report(
    metrics: EvaluationMetrics,
    results: list[TaskResult] | None = None,
    regression: RegressionReport | None = None,
) -> str:
    """Format structured evaluation output as JSON.

    Args:
        metrics: Aggregated run metrics.
        results: Optional list of individual task results.
        regression: Optional regression report comparison.

    Returns:
        JSON string representation.
    """
    payload: dict[str, Any] = {
        "metrics": metrics.to_dict(),
        "regression": None,
        "results": None,
    }

    if regression is not None:
        payload["regression"] = {
            "has_regression": regression.has_regression,
            "regression_count": regression.regression_count,
            "improvement_count": regression.improvement_count,
            "stable_count": regression.stable_count,
            "threshold": regression.threshold,
            "comparisons": {
                k: {
                    "current": v.current_value,
                    "baseline": v.baseline_value,
                    "delta": v.delta,
                    "delta_pct": v.delta_pct,
                    "status": v.status.value,
                    "unit": v.unit,
                }
                for k, v in regression.comparisons.items()
            },
        }

    if results is not None:
        payload["results"] = [
            {
                "task_id": r.task_id,
                "category": r.category,
                "success": r.success,
                "tools_called": r.tools_called,
                "expected_tools": r.expected_tools,
                "tool_accuracy": r.tool_accuracy,
                "unnecessary_tool_calls": r.unnecessary_tool_calls,
                "hallucinated_args": r.hallucinated_args,
                "policy_violations": r.policy_violations,
                "safety_violation": r.safety_violation,
                "prompt_injection_resisted": r.prompt_injection_resisted,
                "data_exfiltrated": r.data_exfiltrated,
                "trust_boundary_violated": r.trust_boundary_violated,
                "latency_seconds": r.latency_seconds,
                "tokens_used": r.tokens_used,
                "cost_usd": r.cost_usd,
                "error_message": r.error_message,
            }
            for r in results
        ]

    return json.dumps(payload, indent=2)


def save_report_file(filepath: str | Path, content: str) -> None:
    """Write formatted evaluation report to filesystem."""
    p = Path(filepath)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
