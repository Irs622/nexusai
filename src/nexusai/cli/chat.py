"""
Interactive CLI Chat Loop for NexusAI with real-time UI event streaming, Voice, and Proactive Automation.
"""

from __future__ import annotations

import getpass
import os
from typing import Any, Callable

from rich.console import Console
from rich.markdown import Markdown
from rich.prompt import Confirm, Prompt

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
from nexusai.security.identity import Identity, Role, TenantContext

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
    from nexusai.cli.key_manager import prompt_and_configure_api_key

    if custom_input is None:
        prompt_and_configure_api_key(interactive=True)

    config = SystemConfig.load_from_yaml()
    # Suppress console Loguru sinks during interactive chat so raw logs don't pollute the user UI.
    # All system logs and security audits are preserved in log files.
    setup_logger(config.logging, console=False)

    # Establish authenticated operator identity for local CLI session
    try:
        current_user = getpass.getuser()
    except Exception:
        current_user = os.getenv("USER") or "local-operator"

    cli_identity = Identity(
        tenant_id="default",
        user_id=current_user,
        role=Role.ADMIN,
        scopes=frozenset(["*"]),
        metadata={"channel": "cli", "platform": "macos"},
    )
    identity_reset_token = TenantContext.set_current_identity(cli_identity)

    # Initialize Scheduler
    scheduler = SchedulerService()
    scheduler.start()

    try:
        # 1. Initialize EventBus & CommandBus
        event_bus = EventBus()
        command_bus = CommandBus()

        FRIENDLY_ACTIONS: dict[str, str] = {
            "workspace_list_directory": "Memeriksa folder proyek",
            "workspace_read_file": "Membaca file",
            "workspace_write_file": "Menulis file",
            "workspace_git_status": "Mengecek status Git",
            "macos_get_active_window": "Mendeteksi aplikasi aktif",
            "macos_send_notification": "Mengirim notifikasi desktop",
            "automation_schedule_reminder": "Menyetel pengingat jadwal",
            "execute_terminal": "Menjalankan perintah terminal",
            "macos_execute_applescript": "Otomatisasi sistem macOS",
            "open_app": "Membuka aplikasi",
            "screen_capture": "Mengambil tangkapan layar",
        }

        # 2. Subscribe Real-Time Progress Stream to EventBus
        async def on_tool_executed(event: ToolExecutedEvent) -> None:
            action_desc = FRIENDLY_ACTIONS.get(event.tool_name, event.tool_name)
            detail = ""
            if event.tool_name == "workspace_read_file" and "path" in event.arguments:
                detail = f" [cyan]({event.arguments['path']})[/cyan]"
            elif event.tool_name == "open_app" and "app_name" in event.arguments:
                detail = f" [cyan]({event.arguments['app_name']})[/cyan]"

            status_color = "green" if event.success else "red"
            symbol = "✔" if event.success else "✘"
            console.print(
                f"  [dim]• {action_desc}{detail} [{status_color}]{symbol}[/{status_color}][/dim]"
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

        # Interactive approval callback for CLI
        async def cli_approval_callback(
            tool_name: str, arguments: dict[str, Any], risk_level: Any
        ) -> bool:
            if custom_input is not None:
                return False

            console.print(
                "\n[bold yellow]🛡️  Izin Diperlukan: Tindakan berikut memerlukan persetujuan Anda[/bold yellow]"
            )
            if tool_name == "execute_terminal":
                cmd = str(arguments.get("command", "")).strip()
                console.print("  [bold]Aksi:[/bold] Menjalankan perintah di Terminal macOS")
                console.print(f"  [bold]Perintah:[/bold] [cyan]{cmd}[/cyan]")
            elif tool_name == "macos_execute_applescript":
                console.print("  [bold]Aksi:[/bold] Menjalankan skrip otomatisasi macOS")
                script_raw = str(arguments.get("script", "")).strip()
                lines = script_raw.splitlines()
                if len(lines) <= 2:
                    console.print(f"  [dim]Deskripsi: {script_raw}[/dim]")
                else:
                    preview = "\n    ".join(lines[:2])
                    console.print(f"  [dim]Deskripsi:\n    {preview}\n    ...[/dim]")
            elif tool_name == "workspace_write_file":
                path = str(arguments.get("file_path") or arguments.get("path", ""))
                console.print(
                    f"  [bold]Aksi:[/bold] Menyimpan perubahan ke file [cyan]{path}[/cyan]"
                )
            else:
                action_desc = FRIENDLY_ACTIONS.get(tool_name, tool_name)
                console.print(f"  [bold]Aksi:[/bold] {action_desc}")
                if arguments:
                    summary = ", ".join(f"{k}={v}" for k, v in arguments.items())
                    console.print(f"  [dim]Detail: {summary}[/dim]")

            return Confirm.ask("  [bold green]Izinkan tindakan ini?[/bold green]", default=False)

        # Register ExecuteToolCommand handler
        handler = ExecuteToolCommandHandler(
            registry, security_guard, event_bus, approval_callback=cli_approval_callback
        )
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
                    user_id=cli_identity.user_id,
                    tenant_id=cli_identity.tenant_id,
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
        TenantContext.reset_current_identity(identity_reset_token)
        scheduler.stop()
