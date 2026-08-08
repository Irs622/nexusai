"""Unit tests for Subprocess Isolation, Provider Resilience Runtime, and Memory Hierarchy."""

import pathlib

import pytest

from nexusai.core.errors import ModelProviderError, ToolExecutionError
from nexusai.memory.hierarchy import MemoryHierarchy
from nexusai.memory.sqlite_memory import SQLiteMemory
from nexusai.models.base import BaseModelProvider
from nexusai.models.runtime import ProviderRuntime
from nexusai.tools.isolation import SubprocessPluginRunner


class MockSuccessProvider(BaseModelProvider):
    async def chat(self, messages: list, tools: list = None) -> dict:
        return {"type": "text", "content": "Primary success"}


class MockFailingProvider(BaseModelProvider):
    async def chat(self, messages: list, tools: list = None) -> dict:
        raise ModelProviderError("API connection timeout")


@pytest.mark.asyncio
async def test_subprocess_isolation_success() -> None:
    runner = SubprocessPluginRunner(timeout_seconds=5.0)
    code = "print('Isolated output')"
    result = await runner.execute_isolated_code(code, {})
    assert "Isolated output" in result["output"]
    assert result["truncated"] is False


@pytest.mark.asyncio
async def test_subprocess_isolation_timeout_kills_process() -> None:
    runner = SubprocessPluginRunner(timeout_seconds=0.5)
    code = "import time; time.sleep(5)"
    with pytest.raises(ToolExecutionError):
        await runner.execute_isolated_code(code, {})


@pytest.mark.asyncio
async def test_provider_resilience_fallback_routing() -> None:
    primary = MockFailingProvider()
    fallback = MockSuccessProvider()
    runtime = ProviderRuntime(
        primary_provider=primary, fallback_provider=fallback, max_retries=2, backoff_seconds=0.1
    )

    response = await runtime.chat_with_resilience([{"role": "user", "content": "Hi"}])
    assert response["content"] == "Primary success"


@pytest.mark.asyncio
async def test_memory_hierarchy(tmp_path: pathlib.Path) -> None:
    db_path = str(tmp_path / "hierarchy_test.db")
    sqlite_mem = SQLiteMemory(db_path=db_path)
    hierarchy = MemoryHierarchy(sqlite_memory=sqlite_mem)
    await hierarchy.initialize()

    await hierarchy.record_interaction("sess_1", "user", "Remember this secret")
    context = await hierarchy.query_relevant_context("sess_1", "secret")
    assert len(context["recent_turns"]) == 1
    assert context["recent_turns"][0]["content"] == "Remember this secret"
