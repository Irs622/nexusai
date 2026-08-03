"""Ollama Wire Payload Translator."""

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
class OllamaTranslator(BaseTranslator):
    """Translator for Ollama local REST wire format."""

    def from_canonical_request(self, request: ChatRequest) -> dict[str, Any]:
        messages = []
        for m in request.messages:
            messages.append({"role": m.role.value, "content": m.content})
        return {
            "model": request.model or "llama3",
            "messages": messages,
            "stream": False,
        }

    def normalize_tool_calls(self, raw_calls: Any) -> list[ToolCall]:
        tool_calls: list[ToolCall] = []
        if not isinstance(raw_calls, list):
            return tool_calls
        for idx, call in enumerate(raw_calls):
            func = call.get("function", {})
            tool_calls.append(
                ToolCall(
                    id=f"ollama_tool_{idx}",
                    name=func.get("name", ""),
                    arguments=func.get("arguments", {}),
                )
            )
        return tool_calls

    def to_canonical_response(self, raw_payload: dict[str, Any], provider_id: str) -> ChatResponse:
        msg_dict = raw_payload.get("message", {})
        content = msg_dict.get("content", "")
        raw_tools = msg_dict.get("tool_calls")
        tool_calls = self.normalize_tool_calls(raw_tools) if raw_tools else None

        msg = ChatMessage(role=MessageRole.ASSISTANT, content=content, tool_calls=tool_calls)
        choice = ChatChoice(index=0, message=msg, finish_reason="done" if raw_payload.get("done") else "stop")

        eval_count = raw_payload.get("eval_count", 0)
        prompt_eval_count = raw_payload.get("prompt_eval_count", 0)
        usage = Usage(
            prompt_tokens=prompt_eval_count,
            completion_tokens=eval_count,
            total_tokens=prompt_eval_count + eval_count,
        )

        return ChatResponse(
            choices=[choice],
            usage=usage,
            model=raw_payload.get("model", "llama3"),
            provider=provider_id,
        )
