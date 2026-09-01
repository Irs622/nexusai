"""
Typer CLI Application Entrypoint for NexusAI.
"""

import asyncio

import typer
import uvicorn
from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv(usecwd=True))

from nexusai.cli.chat import start_chat_session
from nexusai.cli.console import print_banner, print_error, print_info, print_success
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


if __name__ == "__main__":
    app()
