"""
Unit tests for NexusAI FastAPI Web Server and Web UI Dashboard endpoints.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch

from nexusai.api.server import create_app
from nexusai.models.base import BaseModelProvider


class MockApiProvider(BaseModelProvider):
    async def chat(self, messages: list, tools: list | None = None) -> dict:
        return {"type": "text", "content": "Web API Assistant Response"}


@pytest.fixture
def api_client() -> TestClient:
    app = create_app(db_path=":memory:")
    return TestClient(app)


def test_api_status_endpoint(api_client: TestClient) -> None:
    response = api_client.get("/api/status")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "OPERATIONAL"
    assert "context" in data
    assert "strict_security" in data


def test_api_tools_endpoint(api_client: TestClient) -> None:
    response = api_client.get("/api/tools")
    assert response.status_code == 200
    tools = response.json()
    assert isinstance(tools, list)
    tool_names = [t["name"] for t in tools]
    assert "execute_terminal" in tool_names
    assert "macos_open_app" in tool_names
    assert "workspace_git_status" in tool_names


@pytest.mark.asyncio
async def test_api_chat_endpoint(api_client: TestClient) -> None:
    with patch(
        "nexusai.models.openai_provider.OpenAIProvider.chat",
        new_callable=AsyncMock,
        return_value={"type": "text", "content": "Web API Assistant Response"},
    ):
        response = api_client.post(
            "/api/chat",
            json={"prompt": "Hello NexusAI Web", "session_id": "test_web"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "content" in data
        assert data["type"] == "text"


def test_api_tool_execute_endpoint(api_client: TestClient) -> None:
    with patch("asyncio.create_subprocess_shell") as mock_exec:
        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (b"On branch main\nnothing to commit", b"")
        mock_proc.returncode = 0
        mock_exec.return_value = mock_proc

        response = api_client.post(
            "/api/tools/execute",
            json={
                "tool_name": "workspace_git_status",
                "arguments": {},
                "user_confirmed": True,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "workspace_git_status" in data["tool_name"]
