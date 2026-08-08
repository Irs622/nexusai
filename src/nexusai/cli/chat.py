"""
Interactive CLI Chat Loop for NexusAI with real-time UI event streaming, Voice, and Proactive Automation.
"""

from __future__ import annotations

from typing import Any, Callable

from rich.console import Console
from rich.markdown import Markdown
from rich.prompt import Prompt

from nexusai.automation.scheduler import SchedulerService
from nexusai.brain.coordinator import BrainCoordinator
from nexusai.bus.bus import CommandBus, EventBus
from nexusai.bus.commands import ExecuteToolCommand, ExecuteToolCommandHandler
from nexusai.bus.events import ToolExecutedEvent
from nexusai.cli.console import print_banner, print_info, print_success
from nexusai.core.config import SystemConfig
from nexusai.logging.logger import setup_logger
from nexusai.memory.sqlite_memory import SQLiteMemory
from nexusai.models.openai_provider import OpenAIProvider
from nexusai.security.guard import SecurityGuard

# Import default tools
from nexusai.tools.automation import ScheduleReminderTool
from nexusai.tools.macos import GetActiveWindowTool, NotifyTool, OpenAppTool, RawAppleScriptTool
from nexusai.tools.registry import ToolRegistry
from nexusai.tools.system import TerminalTool
from nexusai.tools.vision import ScreenCaptureTool
from nexusai.tools.workspace import GitStatusTool, ListDirectoryTool, ReadFileTool
from nexusai.voice.stt import listen
from nexusai.voice.tts import mac_tts

console = Console()


async def start_chat_session(
    session_id: str = "cli_session",
    custom_input: Callable[[], str] | None = None,
    memory_db_path: str = ":memory:",
    model_provider_override: Any = None,
    use_voice: bool = False,
) -> None:
    """Run the interactive CLI chat loop with Proactive Scheduler lifecycle."""
    print_banner()
    config = SystemConfig.load_from_yaml()
    setup_logger(config.logging)

    # Initialize Scheduler
    scheduler = SchedulerService()
    scheduler.start()

    try:
        # 1. Initialize EventBus & CommandBus
        event_bus = EventBus()
        command_bus = CommandBus()

        # 2. Subscribe Real-Time Progress Stream to EventBus
        async def on_tool_executed(event: ToolExecutedEvent) -> None:
            status_color = "green" if event.success else "red"
            symbol = "✔" if event.success else "✘"
            console.print(
                f"  [dim italic]⚙️ Executed tool '[bold]{event.tool_name}[/bold]' "
                f"([{status_color}]{symbol}[/{status_color}])[/dim italic]"
            )

        event_bus.subscribe(ToolExecutedEvent, on_tool_executed)

        # 3. Setup SecurityGuard & ToolRegistry
        security_guard = SecurityGuard(config.security)
        registry = ToolRegistry()

        # Register default tools
        registry.register(TerminalTool())
        registry.register(OpenAppTool())
        registry.register(GetActiveWindowTool())
        registry.register(RawAppleScriptTool())
        registry.register(NotifyTool())
        registry.register(ScheduleReminderTool(scheduler=scheduler))
        registry.register(ListDirectoryTool())
        registry.register(ReadFileTool())
        registry.register(GitStatusTool())
        registry.register(ScreenCaptureTool())

        # Register ExecuteToolCommand handler
        handler = ExecuteToolCommandHandler(registry, security_guard, event_bus)
        command_bus.register(ExecuteToolCommand, handler)

        # 4. Initialize Memory Store & Brain
        memory = SQLiteMemory(db_path=memory_db_path)
        await memory.initialize_db()

        provider = model_provider_override or OpenAIProvider(settings=config.models)
        coordinator = BrainCoordinator(provider, registry, command_bus, memory=memory)

        mode_str = "Voice (STT/TTS)" if use_voice else "Interactive Text"
        print_success(f"NexusAI AI Operating System Initialized in {mode_str} Mode.")
        print_info("Type your command or 'exit' / 'quit' to terminate.\n")

        while True:
            try:
                if custom_input is not None:
                    user_input = custom_input()
                elif use_voice:
                    console.print("\n[bold green]🎙️ Listening for voice command...[/bold green]")
                    user_input = await listen()
                    if not user_input or not user_input.strip():
                        console.print(
                            "[dim yellow]No speech detected. Falling back to text prompt...[/dim yellow]"
                        )
                        user_input = Prompt.ask("\n[bold cyan]NexusAI ❯[/bold cyan]")
                    else:
                        console.print(f"[bold cyan]Transcribed Voice ❯[/bold cyan] {user_input}")
                else:
                    user_input = Prompt.ask("\n[bold cyan]NexusAI ❯[/bold cyan]")

                if not user_input or not user_input.strip():
                    continue

                cleaned_input = user_input.strip()
                if cleaned_input.lower() in ("exit", "quit", ":q"):
                    print_info("Shutting down NexusAI session. Goodbye!")
                    break

                response = await coordinator.process_user_input(
                    cleaned_input,
                    session_id=session_id,
                )

                content = response.get("content", "")
                console.print(Markdown(content))

                if use_voice and content:
                    await mac_tts(content)

            except (KeyboardInterrupt, EOFError):
                print_info("\nSession interrupted. Goodbye!")
                break
            except Exception as e:
                console.print(f"[bold red]Error:[/bold red] {e}")
                if custom_input is not None:
                    break

    finally:
        scheduler.stop()
