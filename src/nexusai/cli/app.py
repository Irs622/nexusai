"""
Typer CLI Application Entrypoint for NexusAI.
"""

import asyncio
from dotenv import find_dotenv, load_dotenv
import typer
import uvicorn

load_dotenv(find_dotenv(usecwd=True))

from nexusai.cli.chat import start_chat_session
from nexusai.cli.console import print_banner, print_error, print_info, print_success
from nexusai.core.config import SystemConfig
from nexusai.logging.logger import setup_logger

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
        print_info(f"Default Model: {config.models.default_provider} / {config.models.default_model}")
        print_info(f"Strict Security Mode: {config.security.strict_mode}")
    except Exception as e:
        print_error(f"Failed to load status: {e}")


if __name__ == "__main__":
    app()
