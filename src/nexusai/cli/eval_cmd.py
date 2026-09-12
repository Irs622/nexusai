"""
CLI Evaluation Subcommand for NexusAI Agent Runtime.
"""

from pathlib import Path
from typing import Optional

import typer

eval_app = typer.Typer(
    name="eval",
    help="Agent runtime evaluation and regression testing framework",
    add_completion=False,
)


@eval_app.command("run")
def eval_run(
    suite: Optional[str] = typer.Option(
        "evals",
        "--suite",
        "-s",
        help="Evaluation suite path or name (e.g. 'evals', 'file_operations', 'boundary_tests')",
    ),
    baseline: Optional[Path] = typer.Option(
        Path("evals/baselines/v1.0.json"),
        "--baseline",
        "-b",
        help="Path to baseline metrics JSON file for regression comparison",
    ),
    record_baseline: Optional[Path] = typer.Option(
        None,
        "--record-baseline",
        help="Record current evaluation metrics as a new baseline file",
    ),
    safety_only: bool = typer.Option(
        False,
        "--safety-only",
        help="Execute safety and prompt-injection evaluation suites only",
    ),
    format: str = typer.Option(
        "table",
        "--format",
        "-f",
        help="Output format: 'table' (terminal) or 'json'",
    ),
    output: Optional[Path] = typer.Option(
        None,
        "--output",
        "-o",
        help="Path to write evaluation results file",
    ),
    threshold: float = typer.Option(
        0.05,
        "--threshold",
        "-t",
        help="Regression tolerance threshold (default: 0.05 = 5%)",
    ),
) -> None:
    """Run agent evaluation benchmark suite and check for performance regressions."""
    import asyncio
    import sys

    try:
        from evals.runner import run_evaluation
    except ImportError:
        repo_root = Path(__file__).resolve().parent.parent.parent.parent
        if str(repo_root) not in sys.path:
            sys.path.insert(0, str(repo_root))
        from evals.runner import run_evaluation

    # Normalize format for runner ('table' -> 'text')
    fmt = "json" if format.lower() == "json" else "text"

    b_path: str | None = None
    if baseline and str(baseline).strip() and str(baseline).strip() != ".":
        b_path = str(baseline).strip()

    r_path: str | None = None
    if record_baseline and str(record_baseline).strip():
        r_path = str(record_baseline).strip()

    exit_code, _, _ = asyncio.run(
        run_evaluation(
            suite_path=suite or "evals",
            baseline_path=b_path,
            record_baseline=r_path,
            safety_only=safety_only,
            output_format=fmt,
            output_path=str(output) if output else None,
            threshold=threshold,
        )
    )
    raise typer.Exit(code=exit_code)
