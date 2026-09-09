"""Stress & unit test suite verifying the 72-hour sustained soak testing pipeline with chaos injection."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

# Add tools to sys.path to import soak harness runner
repo_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(repo_root))

from tools.run_extended_soak_test import (
    ChaosMetrics,
    ChaosToolPort,
    calculate_percentiles,
    parse_duration_seconds,
    run_extended_soak_harness,
)
from nexusai.brain.ports.tool_port import ToolExecutionRequest


def test_parse_duration_seconds() -> None:
    """Test duration string parsing for seconds, minutes, hours, and days."""
    assert parse_duration_seconds("45s") == 45.0
    assert parse_duration_seconds("10m") == 600.0
    assert parse_duration_seconds("1h") == 3600.0
    assert parse_duration_seconds("24h") == 86400.0
    assert parse_duration_seconds("72h") == 259200.0
    assert parse_duration_seconds("3d") == 259200.0
    assert parse_duration_seconds("120") == 120.0


def test_calculate_percentiles() -> None:
    """Test percentile calculations for empty and populated latency datasets."""
    empty_stats = calculate_percentiles([])
    assert empty_stats["mean"] == 0.0
    assert empty_stats["p50"] == 0.0

    latencies = [1.0, 2.0, 3.0, 4.0, 5.0, 10.0, 20.0, 50.0, 100.0, 200.0]
    stats = calculate_percentiles(latencies)
    assert stats["min"] == 1.0
    assert stats["max"] == 200.0
    assert stats["p50"] == 5.0
    assert stats["p95"] == 200.0
    assert stats["p99"] == 200.0


@pytest.mark.asyncio
async def test_chaos_tool_port_injection() -> None:
    """Test that ChaosToolPort accurately tracks and injects simulated faults."""
    metrics = ChaosMetrics()
    tool_port = ChaosToolPort(chaos_rate=1.0, chaos_metrics=metrics)

    req = ToolExecutionRequest(
        execution_id="test-chaos-1",
        tool_name="test_tool",
        arguments={"payload": "data", "multiplier": 5},
    )

    # 100% chaos will raise or return failure
    for _ in range(20):
        try:
            res = await tool_port.execute(req)
            assert res.success is False
        except (TimeoutError, RuntimeError, asyncio.CancelledError, BaseException):
            pass

    assert metrics.injected_total == 20
    assert (
        metrics.timeouts_handled
        + metrics.step_failures_handled
        + metrics.worker_exceptions_handled
        + metrics.cancellations_handled
    ) == 20


@pytest.mark.stress
@pytest.mark.asyncio
async def test_extended_soak_burst_execution(tmp_path: Path) -> None:
    """Execute burst soak workload with chaos and verify memory, FDs, GC, and reporting."""
    report_dir = tmp_path / "soak_artifacts"

    report = await run_extended_soak_harness(
        max_cycles=300,
        max_duration_sec=3.0,
        workers=4,
        chaos_rate=0.20,
        snapshot_interval_sec=1.0,
        report_dir=report_dir,
        tolerance_growth_pct_24h=10.0,
        verbose=False,
    )

    # 1. Overall Verdict
    assert report["verdict"] == "PASS"
    assert report["total_cycles_executed"] >= 50
    assert report["throughput_cycles_per_sec"] > 0.0

    # 2. Memory Audit & Leak Bounding
    mem = report["memory_audit"]
    assert mem["memory_bounded_verdict"] is True
    assert mem["initial_rss_mb"] > 0.0
    assert mem["final_rss_mb"] > 0.0
    assert "normalized_growth_pct_per_24h" in mem

    # 3. File Descriptor Stability
    res = report["resource_audit"]
    assert res["fd_stable_verdict"] is True
    assert res["initial_fds"] > 0
    assert res["final_fds"] > 0
    assert res["fd_delta"] <= 2

    # 4. Chaos Resilience
    chaos = report["chaos_audit"]
    assert chaos["injected_total"] > 0
    assert (
        chaos["timeouts_handled"]
        + chaos["step_failures_handled"]
        + chaos["worker_exceptions_handled"]
        + chaos["cancellations_handled"]
    ) == chaos["injected_total"]

    # 5. Garbage Collection & Task Audit
    gc_audit = report["gc_audit"]
    assert gc_audit["gc_healthy_verdict"] is True
    assert gc_audit["uncollected_garbage_objects"] == 0
    assert gc_audit["lingering_async_tasks"] <= 2

    # 6. Latency Percentiles
    lat = report["latency_percentiles_ms"]
    assert lat["mean"] > 0.0
    assert lat["p95"] >= lat["p50"]

    # 7. Tracemalloc Allocation Diffs
    assert isinstance(report["top_allocators_diff"], list)

    # 8. Export Evidence Files
    json_path = report_dir / "extended_soak_report.json"
    md_path = report_dir / "extended_soak_report.md"
    assert json_path.is_file()
    assert md_path.is_file()

    with open(json_path, "r", encoding="utf-8") as f:
        saved_json = json.load(f)
    assert saved_json["verdict"] == "PASS"

    with open(md_path, "r", encoding="utf-8") as f:
        saved_md = f.read()
    assert "# NexusAI 72-Hour Sustained Soak & Chaos Test Report" in saved_md
    assert "**Overall Verdict**: `PASS`" in saved_md
