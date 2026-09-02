"""Unit tests for Terminal UI (TUI) Cluster Monitor and CLI commands."""

from __future__ import annotations

import io

import pytest
from rich.console import Console
from typer.testing import CliRunner

from nexusai.cli.app import app
from nexusai.cli.tui.cluster_monitor import ClusterMonitorTUI
from nexusai.infrastructure.distributed.cluster_manager import ClusterOrchestrator
from nexusai.infrastructure.distributed.pool import DistributedWorkerPool
from nexusai.infrastructure.distributed.worker_node import WorkerNode, WorkerNodeStatus


@pytest.mark.unit
def test_cluster_monitor_tui_layout_generation() -> None:
    """Verify ClusterMonitorTUI constructs proper 3-panel Layout hierarchy."""
    pool = DistributedWorkerPool()
    node = WorkerNode(node_id="worker-test-1", max_concurrency=4)
    pool.register_node(node)

    orchestrator = ClusterOrchestrator(pool=pool)
    console = Console(file=io.StringIO(), color_system=None)
    tui = ClusterMonitorTUI(orchestrator=orchestrator, console=console)

    layout = tui.make_layout()
    assert layout["header"] is not None
    assert layout["main"] is not None
    assert layout["footer"] is not None


@pytest.mark.unit
def test_cluster_monitor_tui_workers_table_rendering() -> None:
    """Verify table correctly formats worker node columns and statuses."""
    pool = DistributedWorkerPool()
    node_online = WorkerNode(node_id="worker-01", status=WorkerNodeStatus.ONLINE, max_concurrency=4)
    node_busy = WorkerNode(node_id="worker-02", status=WorkerNodeStatus.BUSY, max_concurrency=8)
    pool.register_node(node_online)
    pool.register_node(node_busy)

    orchestrator = ClusterOrchestrator(pool=pool)
    tui = ClusterMonitorTUI(orchestrator=orchestrator)

    table = tui.generate_workers_table()
    assert len(table.columns) == 9
    assert table.row_count == 2


@pytest.mark.unit
def test_cluster_monitor_tui_render_once() -> None:
    """Verify render_once prints layout without interactive loop."""
    buf = io.StringIO()
    console = Console(file=buf, width=120, force_terminal=False, color_system=None)

    pool = DistributedWorkerPool()
    node = WorkerNode(node_id="worker-snapshot-01", max_concurrency=4)
    pool.register_node(node)

    orchestrator = ClusterOrchestrator(pool=pool)
    tui = ClusterMonitorTUI(orchestrator=orchestrator, console=console)

    tui.render_once()
    output = buf.getvalue()
    assert "NEXUSAI DISTRIBUTED CLUSTER MONITOR" in output
    assert "worker-snapshot-01" in output


@pytest.mark.unit
def test_cli_cluster_status_and_top_commands() -> None:
    """Verify CLI sub-commands 'cluster status' and 'cluster top --once' execute cleanly."""
    runner = CliRunner()

    res_status = runner.invoke(app, ["cluster", "status"])
    assert res_status.exit_code == 0
    assert "NEXUSAI DISTRIBUTED CLUSTER MONITOR" in res_status.stdout

    res_top = runner.invoke(app, ["cluster", "top", "--once"])
    assert res_top.exit_code == 0
    assert "NEXUSAI DISTRIBUTED CLUSTER MONITOR" in res_top.stdout

    res_top_alias = runner.invoke(app, ["top", "--once"])
    assert res_top_alias.exit_code == 0
    assert "NEXUSAI DISTRIBUTED CLUSTER MONITOR" in res_top_alias.stdout
