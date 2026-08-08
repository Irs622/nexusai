"""
Unit tests for Voice Interface (TTS cleaner, mac_tts, and STT listener).
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nexusai.voice.stt import listen
from nexusai.voice.tts import clean_text_for_speech, mac_tts


def test_clean_text_for_speech_markdown_cleaning() -> None:
    raw_markdown = (
        "# NexusAI System\n"
        "Here is **bold** text and *italic* text.\n"
        "Check this code: `print('hello')`\n"
        "```python\ndef test():\n    pass\n```\n"
        "Visit [NexusAI Link](https://nexusai.org) now!"
    )

    cleaned = clean_text_for_speech(raw_markdown)

    assert "#" not in cleaned
    assert "**" not in cleaned
    assert "*" not in cleaned
    assert "`" not in cleaned
    assert "def test()" not in cleaned
    assert "NexusAI Link" in cleaned
    assert "https://" not in cleaned
    assert "Here is bold text and italic text." in cleaned


@pytest.mark.asyncio
async def test_mac_tts_execution() -> None:
    mock_process = AsyncMock()
    mock_process.communicate.return_value = (b"", b"")

    with patch("asyncio.create_subprocess_exec", return_value=mock_process) as mock_exec:
        await mac_tts("**Hello** world")
        mock_exec.assert_called_once_with(
            "say",
            "Hello world",
            stdout=-1,
            stderr=-1,
        )


@pytest.mark.asyncio
async def test_mac_tts_handles_exceptions() -> None:
    with patch("asyncio.create_subprocess_exec", side_effect=Exception("Speech output error")):
        # Should not raise exception
        await mac_tts("Test message")


@pytest.mark.asyncio
async def test_stt_listen_success() -> None:
    mock_rec = MagicMock()
    mock_rec.recognize_google.return_value = "open terminal"
    mock_mic = MagicMock()

    with patch("speech_recognition.Recognizer", return_value=mock_rec):
        with patch("speech_recognition.Microphone", return_value=mock_mic):
            result = await listen(
                recognizer_override=mock_rec,
                microphone_override=mock_mic,
            )
            assert result == "open terminal"


@pytest.mark.asyncio
async def test_stt_listen_fallback_on_exception() -> None:
    mock_rec = MagicMock()
    mock_rec.recognize_google.side_effect = Exception("Unknown audio")
    mock_mic = MagicMock()

    result = await listen(
        recognizer_override=mock_rec,
        microphone_override=mock_mic,
    )
    assert result == ""
