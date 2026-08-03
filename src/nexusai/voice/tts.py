"""
Text-to-Speech Engine utilizing macOS native say utility with Markdown cleaning.
"""

import asyncio
import re


def clean_text_for_speech(text: str) -> str:
    """Clean markdown formatting, code blocks, URLs, and emojis for natural voice synthesis."""
    if not text:
        return ""

    # Remove code blocks
    cleaned = re.sub(r"```[\s\S]*?```", "", text)
    # Remove inline code
    cleaned = re.sub(r"`[^`]*`", "", cleaned)
    # Remove markdown links [text](url) -> text
    cleaned = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", cleaned)
    # Remove headings and list markers
    cleaned = re.sub(r"^[#\*\-\+]\s+", "", cleaned, flags=re.MULTILINE)
    # Remove bold / italic markdown symbols (*, _, ~)
    cleaned = re.sub(r"[\*\_\~]{1,3}", "", cleaned)
    # Remove extra spaces and newlines
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    return cleaned


async def mac_tts(text: str) -> None:
    """Vocalize text using macOS native say utility.

    Args:
        text: Input string to synthesize.
    """
    cleaned = clean_text_for_speech(text)
    if not cleaned:
        return

    try:
        process = await asyncio.create_subprocess_exec(
            "say",
            cleaned,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await process.communicate()
    except Exception:
        pass  # Never let TTS synthesis errors crash the main application
