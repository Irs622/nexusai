"""
StructuredContext and PromptFormatter abstractions for model-agnostic prompt formatting.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import json
from typing import Sequence

from nexusai.memory.domain.record import MemoryRecord


@dataclass
class StructuredContextItem:
    """Item container inside StructuredContext."""

    index: int
    record_id: str
    scope: str
    memory_type: str
    content: str
    metadata: dict


@dataclass
class StructuredContext:
    """Model-agnostic structured context representation of retrieved MemoryRecords."""

    items: list[StructuredContextItem] = field(default_factory=list)
    header: str = "Retrieved Memory Context"


class PromptFormatter(ABC):
    """Abstract contract for model-agnostic prompt formatters."""

    @abstractmethod
    def format(self, context: StructuredContext) -> str:
        """Format StructuredContext into target LLM prompt representation."""
        pass


class MarkdownPromptFormatter(PromptFormatter):
    """Formats StructuredContext into Markdown representation."""

    def format(self, context: StructuredContext) -> str:
        lines = [f"### {context.header}"]
        for item in context.items:
            lines.append(f"\n[{item.index}] Scope: {item.scope} | Type: {item.memory_type}\n{item.content}")
        return "\n".join(lines)


class JSONPromptFormatter(PromptFormatter):
    """Formats StructuredContext into JSON representation."""

    def format(self, context: StructuredContext) -> str:
        data = {
            "header": context.header,
            "memories": [
                {
                    "index": item.index,
                    "id": item.record_id,
                    "scope": item.scope,
                    "type": item.memory_type,
                    "content": item.content,
                }
                for item in context.items
            ],
        }
        return json.dumps(data)


class XMLPromptFormatter(PromptFormatter):
    """Formats StructuredContext into XML representation."""

    def format(self, context: StructuredContext) -> str:
        lines = ["<retrieved_context>"]
        for item in context.items:
            lines.append(
                f'  <memory index="{item.index}" scope="{item.scope}" type="{item.memory_type}">{item.content}</memory>'
            )
        lines.append("</retrieved_context>")
        return "\n".join(lines)


class OpenAIPromptFormatter(PromptFormatter):
    """Formats StructuredContext into OpenAI / GPT system message instructions."""

    def format(self, context: StructuredContext) -> str:
        lines = [f"System Instruction: Use the following {len(context.items)} retrieved context items to answer:"]
        for item in context.items:
            lines.append(f"- [{item.scope.upper()}] ({item.memory_type}): {item.content}")
        return "\n".join(lines)


class ClaudePromptFormatter(PromptFormatter):
    """Formats StructuredContext into Anthropic Claude XML document blocks."""

    def format(self, context: StructuredContext) -> str:
        lines = ["<documents>"]
        for item in context.items:
            lines.append(f'  <document index="{item.index}">')
            lines.append(f"    <source>{item.metadata.get('source', 'unknown')}</source>")
            lines.append(f"    <document_content>{item.content}</document_content>")
            lines.append("  </document>")
        lines.append("</documents>")
        return "\n".join(lines)


class GeminiPromptFormatter(PromptFormatter):
    """Formats StructuredContext into Google Gemini structured system context blocks."""

    def format(self, context: StructuredContext) -> str:
        lines = [f"CONTEXT_HEADER: {context.header}"]
        for item in context.items:
            lines.append(f"GROUNDING_KNOWLEDGE [ID={item.record_id}]: {item.content}")
        return "\n".join(lines)
