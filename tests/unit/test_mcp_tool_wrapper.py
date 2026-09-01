"""Unit tests for McpToolWrapper and BaseTool compliance."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError

from nexusai.core.errors import ToolExecutionError
from nexusai.security.guard import RiskLevel
from nexusai.tools.base import BaseTool
from nexusai.tools.mcp.client import McpClient
from nexusai.tools.mcp.models import (
    McpCallToolResult,
    McpToolContent,
    McpToolDefinition,
)
from nexusai.tools.mcp.tool import McpToolWrapper


@pytest.fixture
def sample_definition() -> McpToolDefinition:
    return McpToolDefinition(
        name="search_database",
        description="Execute a SQL search query against database",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "SQL statement"},
                "limit": {"type": "integer", "description": "Row limit", "default": 10},
            },
            "required": ["query"],
        },
    )


@pytest.fixture
def mock_client() -> MagicMock:
    client = MagicMock(spec=McpClient)
    client.is_connected = True
    client.server_name = "test_db_server"
    client.call_tool = AsyncMock()
    return client


@pytest.mark.asyncio
async def test_mcp_tool_wrapper_compliance(
    mock_client: MagicMock, sample_definition: McpToolDefinition
) -> None:
    """Verify that McpToolWrapper conforms to BaseTool interface and exports valid schema."""
    wrapper = McpToolWrapper(
        client=mock_client,
        definition=sample_definition,
        risk_level=RiskLevel.MEDIUM,
    )

    # 1. BaseTool inheritance
    assert isinstance(wrapper, BaseTool)
    assert wrapper.name == "search_database"
    assert wrapper.description == "Execute a SQL search query against database"
    assert wrapper.risk_level == RiskLevel.MEDIUM

    # 2. Schema export
    schema = wrapper.to_json_schema()
    assert schema["type"] == "function"
    assert schema["function"]["name"] == "search_database"
    assert "query" in schema["function"]["parameters"]["properties"]

    # 3. Dynamic Pydantic schema validation
    valid_args = wrapper.input_schema(query="SELECT * FROM users", limit=5)
    assert valid_args.query == "SELECT * FROM users"
    assert valid_args.limit == 5

    # Missing required field 'query' should fail validation
    with pytest.raises(ValidationError):
        wrapper.input_schema()

    # 4. Execution
    mock_client.call_tool.return_value = McpCallToolResult(
        content=[McpToolContent(type="text", text="Found 3 rows")]
    )

    res = await wrapper.execute(query="SELECT * FROM users", limit=5)
    assert res == "Found 3 rows"
    mock_client.call_tool.assert_awaited_once_with(
        "search_database", {"query": "SELECT * FROM users", "limit": 5}
    )


@pytest.mark.asyncio
async def test_mcp_tool_wrapper_namespacing(
    mock_client: MagicMock, sample_definition: McpToolDefinition
) -> None:
    """Verify that namespacing tools prevents name collisions."""
    wrapper = McpToolWrapper(
        client=mock_client,
        definition=sample_definition,
        namespace_prefix="pg",
    )
    assert wrapper.name == "pg_search_database"
    assert wrapper.mcp_tool_name == "search_database"


@pytest.mark.asyncio
async def test_mcp_tool_wrapper_error_handling(
    mock_client: MagicMock, sample_definition: McpToolDefinition
) -> None:
    """Verify that MCP error responses trigger ToolExecutionError in NexusAI."""
    wrapper = McpToolWrapper(client=mock_client, definition=sample_definition)

    mock_client.call_tool.return_value = McpCallToolResult(
        content=[McpToolContent(type="text", text="Syntax error in SQL")],
        isError=True,
    )

    with pytest.raises(ToolExecutionError) as exc_info:
        await wrapper.execute(query="INVALID SQL")

    assert "reported failure: Syntax error in SQL" in str(exc_info.value)
