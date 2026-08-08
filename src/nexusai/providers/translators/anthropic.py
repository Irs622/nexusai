"""Anthropic Wire Payload Translator."""

from __future__ import annotations

from typing import Any

from nexusai.core.annotations import stable
from nexusai.providers.models import (
    ChatChoice,
    ChatMessage,
    ChatRequest,
    ChatResponse,
    MessageRole,
    ToolCall,
    Usage,
)
from nexusai.providers.translators.base import BaseTranslator


@stable
class AnthropicTranslator(BaseTranslator):
    """Translator for Anthropic Messages wire format (tool_use)."""

    def from_canonical_request(self, request: ChatRequest) -> dict[str, Any]:
        messages = []
        for m in request.messages:
            messages.append({"role": m.role.value, "content": m.content})
        return {
            "model": request.model or "claude-3-5-sonnet-20241022",
            "messages": messages,
            "max_tokens": request.max_tokens or 4096,
        }

    def normalize_tool_calls(self, raw_calls: Any) -> list[ToolCall]:
        tool_calls: list[ToolCall] = []
        if not isinstance(raw_calls, list):
            return tool_calls
        for block in raw_calls:
            if block.get("type") == "tool_use":
                tool_calls.append(
                    ToolCall(
                        id=block.get("id", ""),
                        name=block.get("name", ""),
                        arguments=block.get("input", {}),
                    )
                )
        return tool_calls

    def to_canonical_response(self, raw_payload: dict[str, Any], provider_id: str) -> ChatResponse:
        content_blocks = raw_payload.get("content", [])
        text_content = ""
        raw_tools = []
        for block in content_blocks:
            if block.get("type") == "text":
                text_content += block.get("text", "")
            elif block.get("type") == "tool_use":
                raw_tools.append(block)

        tool_calls = self.normalize_tool_calls(raw_tools) if raw_tools else None
        msg = ChatMessage(role=MessageRole.ASSISTANT, content=text_content, tool_calls=tool_calls)
        choice = ChatChoice(
            index=0, message=msg, finish_reason=raw_payload.get("stop_reason", "end_turn")
        )

        raw_usage = raw_payload.get("usage", {})
        input_tokens = raw_usage.get("input_tokens", 0)
        output_tokens = raw_usage.get("output_tokens", 0)
        thinking_tokens = raw_usage.get("thinking_tokens", 0)
        usage = Usage(
            prompt_tokens=input_tokens,
            completion_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            reasoning_tokens=thinking_tokens,
        )

        return ChatResponse(
            id=raw_payload.get("id", ""),
            choices=[choice],
            usage=usage,
            model=raw_payload.get("model", ""),
            provider=provider_id,
        )
