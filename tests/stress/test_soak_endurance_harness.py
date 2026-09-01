"""Stress test verifying continuous endurance, zero memory leak, and latency stability in soak harness."""

from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

# Add tools to sys.path to import soak harness runner
repo_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(repo_root))

from tools.run_soak_test import run_soak_harness


@pytest.mark.stress
@pytest.mark.asyncio
async def test_continuous_soak_harness_burst(tmp_path: Path) -> None:
    """Execute burst soak workload and assert zero memory leak, clean GC, and valid evidence export."""
    report_dir = tmp_path / "soak_evidence"

    report = await run_soak_harness(
        max_cycles=250,
        max_duration_sec=5.0,
        report_dir=report_dir,
        tolerance_growth_mb=15.0,
        verbose=False,
    )

    # 1. Overall Verdict
    assert report["verdict"] == "PASS"
    assert report["total_cycles_executed"] >= 100

    # 2. Zero Memory Leak
    mem = report["memory_audit"]
    assert mem["leak_free_verdict"] is True
    assert mem["net_rss_growth_mb"] < 15.0
    assert mem["growth_slope_mb_per_1000_cycles"] < 15.0

    # 3. Garbage Collection & Async Tasks
    gc_audit = report["gc_audit"]
    assert gc_audit["gc_healthy_verdict"] is True
    assert gc_audit["uncollected_garbage_objects"] == 0
    assert gc_audit["lingering_async_tasks"] <= 2

    # 4. Latency Percentiles
    lat = report["latency_percentiles_ms"]
    assert lat["mean"] > 0.0
    assert lat["p95"] >= lat["p50"]

    # 5. Evidence Artifacts
    json_path = report_dir / "soak_report.json"
    md_path = report_dir / "soak_report.md"
    assert json_path.is_file()
    assert md_path.is_file()

    with open(json_path, "r", encoding="utf-8") as f:
        saved_data = json.load(f)
    assert saved_data["verdict"] == "PASS"
