"""
Rich Console Output Formatting Manager.
"""

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text

from nexusai import __version__

console = Console()


def print_banner() -> None:
    """Render startup banner for NexusAI AI Operating System."""
    banner_text = Text()
    banner_text.append("   _  __                    ___   ____ \n", style="bold cyan")
    banner_text.append("  / |/ /__ ___ __ _____    / _ | /  _/ \n", style="bold blue")
    banner_text.append(" /    / -_) _// // (_-<   / __ |_/ /   \n", style="bold magenta")
    banner_text.append("/_/|_/\\__/\\__/\\_,_/___/  /_/ |_/___/   \n", style="bold green")
    banner_text.append(f"\n  Personal AI Operating System for macOS v{__version__}\n", style="dim white")

    console.print(Panel(banner_text, border_style="cyan", expand=False))


def print_info(message: str) -> None:
    """Print informative message."""
    console.print(f"[bold blue]ℹ[/bold blue] {message}")


def print_success(message: str) -> None:
    """Print success message."""
    console.print(f"[bold green]✔[/bold green] {message}")


def print_warning(message: str) -> None:
    """Print warning message."""
    console.print(f"[bold yellow]⚠️[/bold yellow] {message}")


def print_error(message: str) -> None:
    """Print error message."""
    console.print(f"[bold red]✘[/bold red] {message}")


def print_markdown(content: str) -> None:
    """Render Markdown content cleanly."""
    console.print(Markdown(content))
