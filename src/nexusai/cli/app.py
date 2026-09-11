"""
Typer CLI Application Entrypoint for NexusAI.
"""

import asyncio

import typer
import uvicorn
from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv(usecwd=True))

from nexusai.cli.chat import start_chat_session
from nexusai.cli.console import print_banner, print_error, print_info, print_success, print_warning
from nexusai.core.config import SystemConfig

app = typer.Typer(
    name="nexusai",
    help="NexusAI: Personal AI Operating System for macOS",
    add_completion=False,
)


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context) -> None:
    """Default entrypoint when no command is specified."""
    if ctx.invoked_subcommand is None:
        print_banner()
        print_info(
            "Use [bold cyan]nexusai chat[/bold cyan] for interactive terminal shell,\n"
            "    [bold cyan]nexusai web[/bold cyan] to launch Hacker Typer Web Dashboard, or\n"
            "    [bold cyan]nexusai --help[/bold cyan] for all options."
        )


@app.command("chat")
def chat(
    voice: bool = typer.Option(False, "--voice", "-v", help="Enable Voice Interface (STT & TTS)"),
) -> None:
    """Launch the interactive NexusAI AI Operating System chat loop."""
    try:
        asyncio.run(start_chat_session(use_voice=voice))
    except (KeyboardInterrupt, EOFError):
        print_info("\nGoodbye!")


@app.command("shell")
def shell(
    voice: bool = typer.Option(False, "--voice", "-v", help="Enable Voice Interface (STT & TTS)"),
) -> None:
    """Alias for chat command."""
    chat(voice=voice)


@app.command("web")
def web(
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Host address to bind Web Server"),
    port: int = typer.Option(8000, "--port", "-p", help="Port number for Web Server"),
) -> None:
    """Launch the Hacker Typer Inspired Web OS Dashboard."""
    print_banner()
    print_success(f"Launching NexusAI Web OS Dashboard at http://{host}:{port}")
    print_info("Press Ctrl+C to terminate Web Server.\n")
    uvicorn.run("nexusai.api.server:app", host=host, port=port, reload=False)


@app.command("status")
def status() -> None:
    """Display system runtime status and configuration summary."""
    try:
        config = SystemConfig.load_from_yaml()
        print_banner()
        print_success("System Status: OPERATIONAL")
        print_info(f"Environment: {config.app.environment}")
        print_info(
            f"Default Model: {config.models.default_provider} / {config.models.default_model}"
        )
        print_info(f"Strict Security Mode: {config.security.strict_mode}")
    except Exception as e:
        print_error(f"Failed to load status: {e}")


mcp_app = typer.Typer(
    name="mcp",
    help="Manage Model Context Protocol (MCP) servers and external tools",
    add_completion=False,
)
app.add_typer(mcp_app, name="mcp")


@mcp_app.command("list")
def mcp_list(
    config_path: str = typer.Option(
        "config/mcp_servers.yaml", "--config", "-c", help="Path to MCP servers config YAML"
    ),
) -> None:
    """List configured Model Context Protocol (MCP) servers and their status."""
    from nexusai.tools.mcp.manager import McpServerManager

    manager = McpServerManager()
    count = manager.load_config_file(config_path)
    print_banner()
    print_info(f"Loaded {count} MCP server configuration(s) from [cyan]{config_path}[/cyan]:\n")

    if not manager.registered_server_names:
        print_info("No MCP servers configured yet. Add servers in config/mcp_servers.yaml")
        return

    for name in manager.registered_server_names:
        cfg = manager._server_configs[name]
        status_tag = (
            "[bold green]ENABLED[/bold green]" if cfg.enabled else "[dim red]DISABLED[/dim red]"
        )
        print_info(
            f"• [bold cyan]{name}[/bold cyan] ({status_tag}) "
            f"[dim]| Cmd: {cfg.command} {' '.join(cfg.args)} | Risk: {cfg.risk_level.value}[/dim]"
        )


@mcp_app.command("ping")
def mcp_ping(
    server_name: str = typer.Argument(..., help="Name of configured MCP server to ping"),
    config_path: str = typer.Option(
        "config/mcp_servers.yaml", "--config", "-c", help="Path to MCP servers config YAML"
    ),
) -> None:
    """Ping an MCP server to verify liveness and communication."""
    from nexusai.tools.mcp.manager import McpServerManager

    manager = McpServerManager()
    manager.load_config_file(config_path)

    if server_name not in manager.registered_server_names:
        print_error(f"MCP server '{server_name}' not found in configuration.")
        raise typer.Exit(code=1)

    async def _do_ping() -> None:
        cfg = manager._server_configs[server_name]
        from nexusai.tools.mcp.client import McpClient

        client = McpClient(cfg)
        try:
            print_info(f"Connecting to MCP server '{server_name}'...")
            await client.start()
            tools = await client.list_tools()
            print_success(f"Connected to '{server_name}' successfully!")
            print_info(f"Discovered {len(tools)} tool(s):")
            for t in tools:
                print_info(f"  - [cyan]{t.name}[/cyan]: {t.description}")
        except Exception as err:
            print_error(f"Failed to connect to '{server_name}': {err}")
        finally:
            await client.stop()

    asyncio.run(_do_ping())


cluster_app = typer.Typer(
    name="cluster",
    help="Manage and monitor distributed worker nodes & scaling",
    add_completion=False,
)
app.add_typer(cluster_app, name="cluster")


@cluster_app.command("status")
def cluster_status(
    config_path: str = typer.Option(
        "config/cluster_workers.yaml", "--config", "-c", help="Path to cluster workers config YAML"
    ),
) -> None:
    """Display real-time distributed worker cluster status snapshot."""
    from nexusai.cli.tui.cluster_monitor import ClusterMonitorTUI

    tui = ClusterMonitorTUI(config_path=config_path)
    tui.render_once()


@cluster_app.command("top")
def cluster_top(
    config_path: str = typer.Option(
        "config/cluster_workers.yaml", "--config", "-c", help="Path to cluster workers config YAML"
    ),
    refresh_rate: float = typer.Option(1.0, "--refresh", "-r", help="Refresh interval in seconds"),
    once: bool = typer.Option(False, "--once", help="Render snapshot once and exit immediately"),
) -> None:
    """Launch interactive Live Terminal UI (TUI) cluster monitor."""
    from nexusai.cli.tui.cluster_monitor import ClusterMonitorTUI

    tui = ClusterMonitorTUI(config_path=config_path)
    tui.run(refresh_rate=refresh_rate, once=once)


@app.command("top")
def top_alias(
    config_path: str = typer.Option(
        "config/cluster_workers.yaml", "--config", "-c", help="Path to cluster workers config YAML"
    ),
    refresh_rate: float = typer.Option(1.0, "--refresh", "-r", help="Refresh interval in seconds"),
    once: bool = typer.Option(False, "--once", help="Render snapshot once and exit immediately"),
) -> None:
    """Launch interactive Live Terminal UI (TUI) cluster monitor (alias for cluster top)."""
    cluster_top(config_path=config_path, refresh_rate=refresh_rate, once=once)


@app.command("create-tool")
def create_tool(
    name: str = typer.Argument(..., help="Snake-case plugin name (e.g. my_tool)"),
    description: str = typer.Option(
        "A new NexusAI tool plugin",
        "--description",
        "-d",
        help="Short description of the tool plugin",
    ),
    output_dir: str = typer.Option(
        "plugins",
        "--output-dir",
        "-o",
        help="Parent directory to create the plugin folder in",
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Preview scaffold output without writing files"
    ),
    overwrite: bool = typer.Option(
        False, "--overwrite", help="Overwrite existing files if they already exist"
    ),
) -> None:
    """Scaffold a new NexusAI tool plugin from the official template."""
    from pathlib import Path

    from nexusai.cli.scaffolding import scaffold_tool

    print_banner()
    try:
        result = scaffold_tool(
            name=name,
            description=description,
            output_dir=Path(output_dir),
            dry_run=dry_run,
            overwrite=overwrite,
        )
        prefix = "[bold yellow]DRY-RUN[/bold yellow] " if dry_run else ""
        print_success(f"{prefix}Tool plugin [bold cyan]{name}[/bold cyan] scaffolded successfully!")
        for f in result.files_written:
            print_info(f"  {'(preview)' if dry_run else '(created)'} [cyan]{f}[/cyan]")
        if not dry_run:
            print_info(
                f"\nNext steps:\n"
                f"  1. Edit [cyan]{output_dir}/{name}/plugin.py[/cyan] to implement your tool\n"
                f"  2. Update [cyan]{output_dir}/{name}/nexusai_manifest.yaml[/cyan] with capabilities\n"
                f"  3. Add the plugin to your runtime configuration\n"
                f"  4. Run [bold]uv run pytest tests/ -k {name}[/bold] to verify"
            )
    except ValueError as exc:
        print_error(str(exc))
        raise typer.Exit(code=1)


@app.command("create-mcp")
def create_mcp(
    name: str = typer.Argument(..., help="Snake-case MCP server name (e.g. my_mcp)"),
    description: str = typer.Option(
        "A new NexusAI MCP server",
        "--description",
        "-d",
        help="Short description of the MCP server",
    ),
    output_dir: str = typer.Option(
        "plugins/mcp",
        "--output-dir",
        "-o",
        help="Parent directory to create the MCP server folder in",
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Preview scaffold output without writing files"
    ),
    overwrite: bool = typer.Option(
        False, "--overwrite", help="Overwrite existing files if they already exist"
    ),
) -> None:
    """Scaffold a new NexusAI MCP server from the official template."""
    from pathlib import Path

    from nexusai.cli.scaffolding import scaffold_mcp

    print_banner()
    try:
        result = scaffold_mcp(
            name=name,
            description=description,
            output_dir=Path(output_dir),
            dry_run=dry_run,
            overwrite=overwrite,
        )
        prefix = "[bold yellow]DRY-RUN[/bold yellow] " if dry_run else ""
        print_success(f"{prefix}MCP server [bold cyan]{name}[/bold cyan] scaffolded successfully!")
        for f in result.files_written:
            print_info(f"  {'(preview)' if dry_run else '(created)'} [cyan]{f}[/cyan]")
        if not dry_run:
            print_info(
                f"\nNext steps:\n"
                f"  1. Edit [cyan]{output_dir}/{name}/server.py[/cyan] to add your tools\n"
                f"  2. Merge [cyan]{output_dir}/{name}/nexusai_mcp.yaml[/cyan] into "
                f"[cyan]config/mcp_servers.yaml[/cyan]\n"
                f"  3. Run [bold]nexusai mcp ping {name}[/bold] to verify connectivity"
            )
    except ValueError as exc:
        print_error(str(exc))
        raise typer.Exit(code=1)


@app.command("doctor")
def doctor(
    format: str = typer.Option(
        "text",
        "--format",
        "-f",
        help="Output format: 'text' (default) or 'json'.",
    ),
) -> None:
    """Run deployment, environment, and security health diagnostics."""
    from nexusai.cli.doctor import CheckStatus, DoctorEngine

    engine = DoctorEngine()
    results = engine.run_all_checks()
    _, exit_code = engine.compute_summary(results)

    if format.lower() == "json":
        typer.echo(engine.format_json(results))
        raise typer.Exit(code=exit_code)

    print_banner()
    print_info("Running NexusAI Environment & Security Diagnostics...\n")

    for r in results:
        title = r.name.replace("_", " ").title()
        if r.status == CheckStatus.PASS:
            print_success(f"[✓] {title}: {r.detail}")
        elif r.status == CheckStatus.FAIL:
            print_error(f"[✗] {title}: {r.detail}")
        else:
            print_warning(f"[⚠] {title}: {r.detail}")

    typer.echo("")
    if exit_code == 0:
        print_success("All diagnostic health checks passed successfully.")
    elif exit_code == 1:
        print_error(
            "Diagnostic check FAILED: One or more critical security/runtime requirements are not met."
        )
    else:
        print_warning(
            "Diagnostic check passed with WARNINGS: Non-critical services may be degraded."
        )

    raise typer.Exit(code=exit_code)


if __name__ == "__main__":
    app()
