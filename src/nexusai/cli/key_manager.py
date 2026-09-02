"""Interactive API Key onboarding and configuration manager for NexusAI CLI."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Tuple

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt

console = Console()


def detect_provider_from_key(key: str) -> Tuple[str, str, str]:
    """Detect provider, default model, and base URL from API key format.

    Returns:
        Tuple of (provider_name, default_model, base_url).
    """
    key_strip = key.strip()
    if key_strip.lower() == "ollama":
        return ("ollama", "llama3.2", "http://localhost:11434/v1")
    if key_strip.startswith("sk-or-v1-"):
        return ("openrouter", "openrouter/auto", "https://openrouter.ai/api/v1")
    if key_strip.startswith("gsk_"):
        return ("groq", "llama-3.1-70b-versatile", "https://api.groq.com/openai/v1")
    if key_strip.startswith("sk-proj-"):
        return ("openai", "gpt-4o-mini", "https://api.openai.com/v1")
    if key_strip.startswith("sk-"):
        # Generic OpenAI or DeepSeek
        return ("openai", "gpt-4o-mini", "https://api.openai.com/v1")

    return ("openai", "gpt-4o-mini", "https://api.openai.com/v1")


def save_key_to_env_file(key: str, env_path: str | Path = ".env") -> Tuple[str, str]:
    """Save detected API key and base URL to target .env file and active os.environ.

    Returns:
        Tuple of (provider_name, model_name).
    """
    env_file = Path(env_path)
    provider, model, base_url = detect_provider_from_key(key)

    # Set in running process environment
    if provider == "openrouter":
        os.environ["OPENROUTER_API_KEY"] = key
        os.environ["OPENAI_API_KEY"] = key
        os.environ["OPENAI_BASE_URL"] = base_url
    elif provider == "ollama":
        os.environ["OPENAI_API_KEY"] = "ollama"
        os.environ["OPENAI_BASE_URL"] = base_url
    else:
        os.environ["OPENAI_API_KEY"] = key
        os.environ["OPENAI_BASE_URL"] = base_url

    os.environ["NEXUSAI_MODELS_DEFAULT_MODEL"] = model

    # Update or append in .env file
    lines: list[str] = []
    if env_file.exists():
        with open(env_file, "r", encoding="utf-8") as f:
            lines = f.readlines()

    keys_to_update = {
        "OPENROUTER_API_KEY": key if provider == "openrouter" else os.getenv("OPENROUTER_API_KEY", ""),
        "OPENAI_API_KEY": "ollama" if provider == "ollama" else key,
        "OPENAI_BASE_URL": base_url,
        "NEXUSAI_MODELS_DEFAULT_MODEL": model,
    }

    updated_keys: set[str] = set()
    new_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        matched_key = None
        for k in keys_to_update:
            if stripped.startswith(f"{k}=") or stripped.startswith(f"#{k}=") or stripped.startswith(f"# {k}="):
                matched_key = k
                break

        if matched_key:
            new_lines.append(f"{matched_key}={keys_to_update[matched_key]}\n")
            updated_keys.add(matched_key)
        else:
            new_lines.append(line)

    for k, v in keys_to_update.items():
        if k not in updated_keys and v:
            new_lines.append(f"{k}={v}\n")

    with open(env_file, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

    return provider, model


def prompt_and_configure_api_key(interactive: bool = True) -> None:
    """Prompt user to paste API key on terminal entry if interactive, and configure runtime."""
    if not interactive or os.getenv("CI") == "1":
        return

    current_key = os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY") or ""
    has_key = bool(current_key.strip())

    header_msg = (
        "[bold cyan]🔑 Masukkan / Paste API Key AI Anda untuk memulai:[/bold cyan]\n"
        "[dim]• OpenRouter  : [/dim][yellow]sk-or-v1-...[/yellow] [dim](Claude 3.5, Llama 3, Gemini, Mistral)[/dim]\n"
        "[dim]• Groq        : [/dim][yellow]gsk_...[/yellow]       [dim](Super cepat, free tier harian besar)[/dim]\n"
        "[dim]• OpenAI      : [/dim][yellow]sk-proj-...[/yellow]   [dim](GPT-4o, GPT-4o-mini)[/dim]\n"
        "[dim]• DeepSeek    : [/dim][yellow]sk-...[/yellow]        [dim](DeepSeek-Chat / Coder)[/dim]\n"
        "[dim]• Offline Mac : [/dim][yellow]ollama[/yellow]        [dim](Lokal tanpa kuota via Ollama)[/dim]"
    )

    console.print(Panel(header_msg, title="[bold green]NexusAI Model Setup[/bold green]", border_style="cyan"))

    if has_key:
        masked = current_key[:8] + "..." + current_key[-4:] if len(current_key) > 14 else "***"
        prompt_text = (
            f"[bold white]Paste API Key baru[/bold white] "
            f"[dim](Tekan Enter untuk gunakan key saat ini: {masked})[/dim]"
        )
        user_key = Prompt.ask(prompt_text, default="")
        if not user_key.strip():
            # Use existing key
            return
    else:
        user_key = Prompt.ask("[bold white]Paste API Key Anda di sini[/bold white]")

    clean_key = user_key.strip()
    if clean_key:
        provider, model = save_key_to_env_file(clean_key)
        console.print(
            f"[bold green]✔ API Key berhasil disimpan![/bold green] "
            f"[dim]Provider: [cyan]{provider}[/cyan] | Model: [cyan]{model}[/cyan][/dim]\n"
        )
