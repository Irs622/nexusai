"""
Unit tests for evals.runner module.
"""

import pytest

from evals.runner import (
    EvalTask,
    EvaluationRunner,
    load_tasks_from_path,
    run_evaluation,
)


def test_load_tasks_from_path_discovers_tasks() -> None:
    """Loading tasks from 'evals' discovers tasks across functional and safety suites."""
    tasks = load_tasks_from_path("evals")
    assert len(tasks) >= 36
    task_ids = [t.id for t in tasks]
    assert "eval_read_file" in task_ids
    assert "eval_debug_error" in task_ids
    assert "safety_no_ssh_read" in task_ids


def test_load_tasks_safety_only_filters() -> None:
    """Using safety_only flag should only load safety test tasks."""
    tasks = load_tasks_from_path("evals", safety_only=True)
    assert len(tasks) >= 16
    for t in tasks:
        assert (
            t.category
            in ("safety", "privilege_escalation", "data_exfiltration", "prompt_injection")
            or "safety" in t.id
            or "injection" in t.id
        )


def test_load_tasks_missing_path_raises() -> None:
    """Non-existent path raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        load_tasks_from_path("non_existent_directory_xyz")


@pytest.mark.asyncio
async def test_evaluation_runner_single_task() -> None:
    """Runner executes an individual task and computes result structure."""
    runner = EvaluationRunner()
    task = EvalTask(
        id="test_read",
        category="file_operations",
        description="Test file read",
        prompt="Read the config file",
        expected_tools=["read_file"],
        expected_outcome="SUCCESS",
    )
    result = await runner.run_single_task(task)
    assert result.task_id == "test_read"
    assert result.success is True
    assert result.tool_accuracy == 1.0
    assert result.latency_seconds >= 0.0


@pytest.mark.asyncio
async def test_run_evaluation_clean_baseline() -> None:
    """Full evaluation run against golden baseline returns exit code 0."""
    exit_code, metrics, regression = await run_evaluation(
        suite_path="evals",
        baseline_path="evals/baselines/v1.0.json",
        output_format="text",
    )
    assert exit_code == 0
    assert metrics.total_tasks >= 36
    assert regression is not None
    assert not regression.has_regression


@pytest.mark.asyncio
async def test_run_evaluation_missing_baseline_exit_code_2() -> None:
    """Missing baseline path should return error exit code 2."""
    exit_code, _, _ = await run_evaluation(
        suite_path="evals",
        baseline_path="evals/baselines/non_existent.json",
    )
    assert exit_code == 2
