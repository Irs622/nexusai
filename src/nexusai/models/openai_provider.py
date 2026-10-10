"""
OpenAI & Compatible Async API Model Provider for NexusAI with Multimodal Vision support.
"""

from __future__ import annotations

import ast
import asyncio
import base64
import json
import os
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI

from nexusai.core.config import ModelSettings
from nexusai.core.errors import ConfigurationError, ModelProviderError
from nexusai.logging.logger import logger
from nexusai.models.base import BaseModelProvider

_ALLOWED_IMAGE_EXTENSIONS: frozenset[str] = frozenset(
    {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
)
_MAX_IMAGE_BYTES: int = 5 * 1024 * 1024  # 5 MB


def _get_workspace_root() -> Path:
    return Path(os.getenv("NEXUSAI_WORKSPACE_ROOT", ".")).resolve()


def _validate_image_path(raw_path: str) -> tuple[Path, str | None]:
    """Validate image path against workspace root. Returns (resolved_path, error_message)."""
    workspace_root = _get_workspace_root()
    try:
        candidate = Path(raw_path).resolve()
    except Exception:
        return Path(raw_path), "Error: Invalid image path."

    # Reject symlinks that resolve outside workspace
    if Path(raw_path).is_symlink():
        try:
            candidate.relative_to(workspace_root)
        except ValueError:
            return candidate, "Error: Symlink resolves outside allowed workspace root."

    # Enforce workspace containment
    try:
        candidate.relative_to(workspace_root)
    except ValueError:
        return candidate, "Error: Image path is outside allowed workspace root."

    # Enforce file extension
    if candidate.suffix.lower() not in _ALLOWED_IMAGE_EXTENSIONS:
        return candidate, f"Error: File type '{candidate.suffix}' is not an allowed image type."

    return candidate, None


async def process_multimodal_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Transform messages containing image_path payloads into OpenAI base64 image_url objects asynchronously."""
    formatted_messages: list[dict[str, Any]] = []

    for msg in messages:
        msg_copy = dict(msg)
        content = msg_copy.get("content")

        if isinstance(content, str) and "image_path" in content:
            try:
                data = None
                if content.strip().startswith("{") and content.strip().endswith("}"):
                    data = json.loads(content)
                elif "type" in content and "path" in content:
                    try:
                        data = ast.literal_eval(content)
                    except Exception:
                        data = None

                if isinstance(data, dict) and data.get("type") == "image_path":
                    img_path, err = _validate_image_path(data.get("path", ""))
                    if err:
                        msg_copy["content"] = err
                    elif img_path.exists() and img_path.is_file():
                        # Enforce size ceiling before reading
                        if img_path.stat().st_size > _MAX_IMAGE_BYTES:
                            msg_copy["content"] = (
                                "Error: Image file exceeds maximum allowed size (5MB)."
                            )
                        else:
                            img_bytes = await asyncio.to_thread(img_path.read_bytes)
                            b64_str = base64.b64encode(img_bytes).decode("utf-8")
                            msg_copy["content"] = [
                                {"type": "text", "text": "Screenshot captured from user screen."},
                                {
                                    "type": "image_url",
                                    "image_url": {"url": f"data:image/png;base64,{b64_str}"},
                                },
                            ]
                    else:
                        msg_copy["content"] = f"Error: Screenshot file not found at '{img_path}'."
            except Exception:
                pass  # Fall back to original text if parsing fails

        formatted_messages.append(msg_copy)

    return formatted_messages


class OpenAIProvider(BaseModelProvider):
    """Model provider adapter using OpenAI Async API with Multimodal Vision support."""

    def __init__(
        self,
        settings: ModelSettings | None = None,
        api_key: str | None = None,
        client: AsyncOpenAI | None = None,
    ) -> None:
        self.settings = settings or ModelSettings()
        self.model = self.settings.default_model
        resolved_key = api_key or os.getenv("OPENAI_API_KEY") or os.getenv("OPENROUTER_API_KEY")
        base_url = (
            self.settings.base_url
            or os.getenv("OPENAI_BASE_URL")
            or os.getenv("OPENROUTER_BASE_URL")
        )

        if client is not None:
            self.client = client
        elif resolved_key:
            client_kwargs: dict[str, Any] = {"api_key": resolved_key}
            if base_url:
                client_kwargs["base_url"] = base_url
            self.client = AsyncOpenAI(**client_kwargs)
        else:
            raise ConfigurationError(
                "OPENAI_API_KEY environment variable or api_key parameter is missing."
            )

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Send chat messages to OpenAI API and parse normalized response.

        The ``BaseModelProvider`` contract returns at most one tool call per model
        turn (ADR 0036), so parallel tool calling is disabled whenever tools are
        supplied. If a backend ignores that flag and still returns several calls,
        only the first is executed and the rest are logged; the agent loop will
        request them again on the next turn.
        """
        formatted_messages = await process_multimodal_messages(messages)

        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": formatted_messages,
            "temperature": self.settings.temperature,
            "max_tokens": self.settings.max_tokens,
            "timeout": float(self.settings.timeout_seconds),
        }

        if tools:
            kwargs["tools"] = tools
            kwargs["parallel_tool_calls"] = False

        try:
            response = await self.client.chat.completions.create(**kwargs)
            if not hasattr(response, "choices"):
                raise ModelProviderError("Unexpected response format from OpenAI API")
            message = response.choices[0].message

            if message.tool_calls:
                if len(message.tool_calls) > 1:
                    dropped = [
                        getattr(getattr(tc, "function", None), "name", "?")
                        for tc in message.tool_calls[1:]
                    ]
                    logger.warning(
                        "Model returned {} tool calls despite parallel_tool_calls=False; "
                        "executing only the first, ignoring: {}",
                        len(message.tool_calls),
                        dropped,
                    )
                first_call = message.tool_calls[0]
                func = getattr(first_call, "function", None)
                if func is not None:
                    tool_name = func.name
                    try:
                        arguments = json.loads(func.arguments)
                    except Exception as je:
                        raise ModelProviderError(
                            f"Failed to parse tool call JSON arguments: {je}"
                        ) from je

                    return {
                        "type": "tool_call",
                        "tool_name": tool_name,
                        "arguments": arguments,
                    }

            return {
                "type": "text",
                "content": message.content or "",
            }

        except ModelProviderError:
            raise
        except Exception as e:
            raise ModelProviderError(f"OpenAI API call failed: {e}") from e
