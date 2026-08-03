"""Gemini Wire Payload Translator."""

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
class GeminiTranslator(BaseTranslator):
    """Translator for Google Gemini REST wire format (function_call)."""

    def from_canonical_request(self, request: ChatRequest) -> dict[str, Any]:
        contents = []
        for m in request.messages:
            role = "user" if m.role == MessageRole.USER else "model"
            contents.append({"role": role, "parts": [{"text": m.content}]})
        return {"contents": contents}

    def normalize_tool_calls(self, raw_calls: Any) -> list[ToolCall]:
        tool_calls: list[ToolCall] = []
        if not isinstance(raw_calls, list):
            return tool_calls
        for part in raw_calls:
            if "functionCall" in part:
                fc = part["functionCall"]
                tool_calls.append(
                    ToolCall(
                        id=fc.get("name", "func_1"),
                        name=fc.get("name", ""),
                        arguments=fc.get("args", {}),
                    )
                )
        return tool_calls

    def to_canonical_response(self, raw_payload: dict[str, Any], provider_id: str) -> ChatResponse:
        candidates = raw_payload.get("candidates", [])
        choices: list[ChatChoice] = []
        for idx, c in enumerate(candidates):
            content = c.get("content", {})
            parts = content.get("parts", [])
            text_str = ""
            raw_tools = []
            for p in parts:
                if "text" in p:
                    text_str += p["text"]
                elif "functionCall" in p:
                    raw_tools.append(p)
            tool_calls = self.normalize_tool_calls(raw_tools) if raw_tools else None
            msg = ChatMessage(role=MessageRole.ASSISTANT, content=text_str, tool_calls=tool_calls)
            choices.append(ChatChoice(index=idx, message=msg, finish_reason=c.get("finishReason", "STOP")))

        usage_meta = raw_payload.get("usageMetadata", {})
        usage = Usage(
            prompt_tokens=usage_meta.get("promptTokenCount", 0),
            completion_tokens=usage_meta.get("candidatesTokenCount", 0),
            total_tokens=usage_meta.get("totalTokenCount", 0),
        )

        return ChatResponse(
            choices=choices,
            usage=usage,
            model="gemini-1.5-pro",
            provider=provider_id,
        )
