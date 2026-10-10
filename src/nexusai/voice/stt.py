"""
Speech-to-Text Engine utilizing SpeechRecognition library and microphone input.
"""

import asyncio
from typing import Any

from nexusai.logging.logger import logger

_AUDIO_INSTALL_HINT = (
    "Microphone input requires PyAudio. Install the audio extra: "
    "pip install 'nexusai[audio]' (macOS: brew install portaudio first; "
    "Debian/Ubuntu: apt-get install portaudio19-dev libasound2-dev)."
)


def _record_and_transcribe(
    recognizer_override: Any = None,
    microphone_override: Any = None,
) -> str:
    """Record microphone audio and transcribe via Google Speech Recognition API."""
    try:
        import speech_recognition as sr

        recognizer = recognizer_override or sr.Recognizer()
        mic = microphone_override or sr.Microphone()

        with mic as source:
            recognizer.adjust_for_ambient_noise(source, duration=0.3)
            audio = recognizer.listen(source, timeout=5, phrase_time_limit=10)

        text = recognizer.recognize_google(audio)
        return str(text).strip()
    except (ImportError, AttributeError) as exc:
        # SpeechRecognition raises AttributeError("Could not find PyAudio...") when the
        # native audio stack is absent; degrade to text-only input.
        logger.warning("Voice input unavailable: {}. {}", exc, _AUDIO_INSTALL_HINT)
        return ""
    except Exception as exc:
        # Permission denied, timeout, or unintelligible audio: treat as no input.
        logger.debug("Speech recognition produced no result: {!r}", exc)
        return ""


async def listen(
    recognizer_override: Any = None,
    microphone_override: Any = None,
) -> str:
    """Listen for microphone input asynchronously and return transcribed text string.

    Returns empty string gracefully if microphone permission is denied or audio is unintelligible.
    """
    try:
        return await asyncio.to_thread(
            _record_and_transcribe,
            recognizer_override,
            microphone_override,
        )
    except Exception as exc:
        logger.debug("Speech recognition worker failed: {!r}", exc)
        return ""
