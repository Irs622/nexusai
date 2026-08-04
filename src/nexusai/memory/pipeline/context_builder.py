"""
ContextBuilder for converting MemoryRecords to StructuredContext and formatting with PromptFormatter DI.
"""

from __future__ import annotations

from typing import Sequence

from nexusai.memory.contracts.retrieval import QueryResult
from nexusai.memory.domain.record import MemoryRecord
from nexusai.memory.pipeline.formatters import (
    MarkdownPromptFormatter,
    PromptFormatter,
    StructuredContext,
    StructuredContextItem,
)


class ContextBuilder:
    """ContextBuilder converting MemoryRecords to StructuredContext formatted with PromptFormatter DI."""

    def __init__(
        self,
        formatter: PromptFormatter | None = None,
        strategy: str = "conversation",
        header: str = "Retrieved Memory Context",
    ) -> None:
        self._formatter = formatter or MarkdownPromptFormatter()
        self._strategy = strategy
        self._header = header

    def build_structured(self, records_or_result: Sequence[MemoryRecord] | QueryResult) -> StructuredContext:
        """Build StructuredContext representation from MemoryRecords."""
        records_list: list[MemoryRecord]
        if isinstance(records_or_result, QueryResult):
            records_list = list(records_or_result.records)
        else:
            records_list = list(records_or_result)

        if self._strategy == "chronological":
            records_list.sort(key=lambda r: r.metadata.created_at)

        items = []
        for idx, rec in enumerate(records_list, start=1):
            text = rec.content.summary or rec.content.raw_text
            items.append(
                StructuredContextItem(
                    index=idx,
                    record_id=rec.id,
                    scope=rec.scope.value,
                    memory_type=rec.memory_type.value,
                    content=text.strip(),
                    metadata={"source": rec.metadata.source, "tags": list(rec.metadata.tags)},
                )
            )

        return StructuredContext(items=items, header=self._header)

    def build_context(
        self,
        records_or_result: Sequence[MemoryRecord] | QueryResult,
        max_tokens_approx: int = 2000,
    ) -> str:
        """Build formatted string prompt context via PromptFormatter."""
        structured = self.build_structured(records_or_result)
        return self._formatter.format(structured)
