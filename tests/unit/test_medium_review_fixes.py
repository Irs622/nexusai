"""Regression tests for the medium-severity code review fixes."""

from __future__ import annotations

import shlex
import sys
from pathlib import Path

import pytest

from nexusai.brain.ports.tool_port import ToolExecutionRequest
from nexusai.infrastructure.tools.process_tool import ProcessTool
from nexusai.memory.storage.file import FileMemoryStore
from nexusai.memory.vector.pgvector import PgVectorStore


@pytest.mark.parametrize("record_id", ["../escape", "a/b", "..", ""])
@pytest.mark.asyncio
async def test_file_memory_store_rejects_path_traversal(tmp_path: Path, record_id: str) -> None:
    store = FileMemoryStore(tmp_path / "store")
    with pytest.raises(ValueError):
        await store.get(record_id)


@pytest.mark.parametrize("table_name", ["vectors; DROP TABLE users", "1abc", "a.b"])
def test_pgvector_rejects_unsafe_table_names(table_name: str) -> None:
    with pytest.raises(ValueError):
        PgVectorStore(table_name=table_name)


def test_pgvector_rejects_unknown_index_type() -> None:
    with pytest.raises(ValueError):
        PgVectorStore(index_type="hnsw; DROP TABLE x")


@pytest.mark.asyncio
async def test_process_tool_bounds_output_and_honours_quotes() -> None:
    tool = ProcessTool(max_output_bytes=10)

    big = await tool.execute(
        ToolExecutionRequest(
            tool_name="process_tool",
            arguments={"argv": [sys.executable, "-c", "print('x' * 100000)"]},
            execution_id="p1",
        )
    )
    assert big.success is True
    assert big.output == "x" * 10

    quoted = await tool.execute(
        ToolExecutionRequest(
            tool_name="process_tool",
            arguments={"command": f"{shlex.quote(sys.executable)} -c \"print('a b')\""},
            execution_id="p2",
        )
    )
    assert quoted.success is True
    assert quoted.output.strip() == "a b"
