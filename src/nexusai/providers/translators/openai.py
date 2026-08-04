"""OpenAI Wire Payload Translator."""

from __future__ import annotations

import json
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
class OpenAITranslator(BaseTranslator):
    """Translator for OpenAI JSON wire format (tool_calls)."""

    def from_canonical_request(self, request: ChatRequest) -> dict[str, Any]:
        messages = []
        for m in request.messages:
            messages.append({"role": m.role.value, "content": m.content})
        payload: dict[str, Any] = {
            "model": request.model or "gpt-4o",
            "messages": messages,
            "temperature": request.temperature,
            "top_p": request.top_p,
        }
        if request.max_tokens:
            payload["max_tokens"] = request.max_tokens
        return payload

    def normalize_tool_calls(self, raw_calls: Any) -> list[ToolCall]:
        tool_calls: list[ToolCall] = []
        if not isinstance(raw_calls, list):
            return tool_calls
        for call in raw_calls:
            call_id = call.get("id", "")
            func = call.get("function", {})
            name = func.get("name", "")
            raw_args = func.get("arguments", "{}")
            if isinstance(raw_args, str):
                try:
                    args = json.loads(raw_args)
                except Exception:
                    args = {}
            else:
                args = raw_args
            tool_calls.append(ToolCall(id=call_id, name=name, arguments=args))
        return tool_calls

    def to_canonical_response(self, raw_payload: dict[str, Any], provider_id: str) -> ChatResponse:
        raw_choices = raw_payload.get("choices", [])
        choices: list[ChatChoice] = []
        for idx, c in enumerate(raw_choices):
            msg = c.get("message", {})
            role = MessageRole(msg.get("role", "assistant"))
            content = msg.get("content", "")
            raw_tools = msg.get("tool_calls")
            tool_calls = self.normalize_tool_calls(raw_tools) if raw_tools else None

            chat_msg = ChatMessage(role=role, content=content, tool_calls=tool_calls)
            choices.append(
                ChatChoice(
                    index=idx,
                    message=chat_msg,
                    finish_reason=c.get("finish_reason", "stop"),
                )
            )

        raw_usage = raw_payload.get("usage", {})
        details = raw_usage.get("completion_tokens_details", {}) or {}
        reasoning_tokens = details.get("reasoning_tokens", 0) if isinstance(details, dict) else 0

        usage = Usage(
            prompt_tokens=raw_usage.get("prompt_tokens", 0),
            completion_tokens=raw_usage.get("completion_tokens", 0),
            total_tokens=raw_usage.get("total_tokens", 0),
            reasoning_tokens=reasoning_tokens,
        )

        return ChatResponse(
            id=raw_payload.get("id", ""),
            choices=choices,
            usage=usage,
            model=raw_payload.get("model", ""),
            provider=provider_id,
        )
