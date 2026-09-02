"""Terminal UI (TUI) Live Monitor for NexusAI Distributed Worker Cluster."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import time

import psutil
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
import yaml

from nexusai.infrastructure.distributed.cluster_manager import ClusterOrchestrator
from nexusai.infrastructure.distributed.pool import DistributedWorkerPool
from nexusai.infrastructure.distributed.worker_node import WorkerNodeStatus


class ClusterMonitorTUI:
    """Interactive Rich Terminal UI displaying real-time cluster metrics, nodes, and scaling events."""

    def __init__(
        self,
        config_path: str | Path = "config/cluster_workers.yaml",
        orchestrator: ClusterOrchestrator | None = None,
        console: Console | None = None,
    ) -> None:
        self.config_path = Path(config_path)
        self.console = console or Console()

        if orchestrator is not None:
            self.orchestrator = orchestrator
        else:
            pool = self._load_pool()
            self.orchestrator = ClusterOrchestrator(pool=pool)

    def _load_pool(self) -> DistributedWorkerPool:
        """Load worker pool from YAML config or create default fallback pool."""
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                return DistributedWorkerPool.from_config_dict(data)
            except Exception:
                pass
        return DistributedWorkerPool()

    def generate_header(self) -> Panel:
        """Generate top header panel with system vitals and timestamp."""
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        cpu_pct = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory()

        header_text = Text()
        header_text.append("⚡ NEXUSAI DISTRIBUTED CLUSTER MONITOR ⚡", style="bold cyan")
        header_text.append(f"  |  Time: {now_str}", style="dim white")
        header_text.append(f"  |  CPU: {cpu_pct:.1f}%", style="green" if cpu_pct < 70 else "red")
        header_text.append(
            f"  |  RAM: {mem.percent:.1f}% ({mem.used // (1024*1024)}MB)",
            style="green" if mem.percent < 80 else "yellow",
        )

        return Panel(header_text, style="cyan", border_style="bold blue")

    def generate_workers_table(self) -> Table:
        """Generate formatted table of registered worker nodes."""
        table = Table(
            title="Registered Cluster Worker Nodes",
            title_style="bold white",
            expand=True,
            border_style="blue",
            header_style="bold cyan",
        )
        table.add_column("Node ID", style="bold yellow", no_wrap=True)
        table.add_column("Status", justify="center")
        table.add_column("Endpoint", style="dim cyan")
        table.add_column("Concurrency", justify="right")
        table.add_column("Active", justify="right")
        table.add_column("Executed", justify="right")
        table.add_column("Failed", justify="right")
        table.add_column("Avg Latency", justify="right")
        table.add_column("Heartbeat", justify="right", style="dim")

        status_styles = {
            WorkerNodeStatus.ONLINE: "[bold green]ONLINE[/bold green]",
            WorkerNodeStatus.BUSY: "[bold yellow]BUSY[/bold yellow]",
            WorkerNodeStatus.DRAINING: "[bold magenta]DRAINING[/bold magenta]",
            WorkerNodeStatus.OFFLINE: "[bold red]OFFLINE[/bold red]",
        }

        now = time.time()
        for node_id, node in self.orchestrator.pool._nodes.items():
            st_text = status_styles.get(node.status, str(node.status.value))
            heartbeat_age = f"{max(0.0, now - node.metrics.last_heartbeat):.1f}s ago"
            failed_color = "red" if node.metrics.failed_tasks > 0 else "dim"

            table.add_row(
                node_id,
                st_text,
                node.endpoint,
                str(node.max_concurrency),
                f"[bold cyan]{node.metrics.active_tasks}[/bold cyan]",
                str(node.metrics.total_tasks_executed),
                f"[{failed_color}]{node.metrics.failed_tasks}[/{failed_color}]",
                f"{node.metrics.avg_latency_ms:.1f}ms",
                heartbeat_age,
            )

        if not self.orchestrator.pool._nodes:
            table.add_row("No workers registered", "-", "-", "-", "-", "-", "-", "-", "-")

        return table

    def generate_telemetry_panel(self) -> Panel:
        """Generate summary panel of cluster utilization and recent scaling actions."""
        snapshot = self.orchestrator.get_cluster_snapshot()

        total = snapshot["total_nodes"]
        healthy = snapshot["healthy_nodes"]
        capacity = snapshot["total_capacity"]
        active = snapshot["active_tasks"]
        util = snapshot["utilization_ratio"] * 100

        util_color = "green" if util < 70 else ("yellow" if util < 85 else "bold red")

        content = Text()
        content.append(f"Cluster Capacity: {healthy}/{total} Nodes Online  |  ", style="bold white")
        content.append(f"Slot Utilization: {active}/{capacity} ({util:.1f}%)\n", style=util_color)

        content.append("\nRecent Auto-Scaler Events:\n", style="bold cyan")
        recent_events = snapshot.get("recent_scaling_events", [])
        if recent_events:
            for ev in recent_events[:4]:
                dir_color = "bold green" if ev["direction"] == "SCALE_OUT" else "bold magenta"
                content.append(
                    f"  • [{dir_color}]{ev['direction']}[/{dir_color}] "
                    f"Target: [yellow]{ev['target_node']}[/yellow] "
                    f"Nodes: {ev['nodes_before']} -> {ev['nodes_after']} "
                    f"({ev['reason']})\n"
                )
        else:
            content.append("  [dim]No scaling actions yet (Cluster load is optimal)[/dim]\n")

        content.append("\n[dim]Press Ctrl+C to exit monitor loop.[/dim]", style="dim italic")

        return Panel(content, title="Auto-Scaler & Telemetry", border_style="blue")

    def make_layout(self) -> Layout:
        """Construct full TUI layout containing header, worker table, and telemetry panel."""
        layout = Layout()
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="main", ratio=1),
            Layout(name="footer", size=8),
        )
        layout["header"].update(self.generate_header())
        layout["main"].update(self.generate_workers_table())
        layout["footer"].update(self.generate_telemetry_panel())
        return layout

    def render_once(self) -> None:
        """Render snapshot layout once to terminal without interactive loop."""
        self.console.print(self.make_layout())

    def run(self, refresh_rate: float = 1.0, once: bool = False) -> None:
        """Execute interactive Live TUI monitor loop."""
        if once:
            self.render_once()
            return

        with Live(self.make_layout(), console=self.console, refresh_per_second=int(1.0 / max(0.2, refresh_rate))) as live:
            try:
                while True:
                    live.update(self.make_layout())
                    time.sleep(refresh_rate)
            except KeyboardInterrupt:
                pass
