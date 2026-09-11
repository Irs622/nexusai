"""
Unit tests for NexusAI FastAPI Web Server and Web UI Dashboard endpoints.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from nexusai.api.server import create_app
from nexusai.models.base import BaseModelProvider


class MockApiProvider(BaseModelProvider):
    async def chat(self, messages: list, tools: list | None = None) -> dict:
        return {"type": "text", "content": "Web API Assistant Response"}


@pytest.fixture
def api_client() -> TestClient:
    app = create_app(db_path=":memory:")
    return TestClient(app, headers={"X-NexusAI-API-Key": "nx_test_admin_key_123"})


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
            json={
                "prompt": "Hello NexusAI Web",
                "session_id": "test_web",
                "approval_token": "nexus_appr_mock",
            },
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

        # LOW risk tool succeeds without approval token
        response = api_client.post(
            "/api/tools/execute",
            json={
                "tool_name": "workspace_git_status",
                "arguments": {},
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "workspace_git_status" in data["tool_name"]


def test_api_high_risk_tool_requires_approval_token(api_client: TestClient) -> None:
    # HIGH risk tool (execute_terminal) without token must return 403 Forbidden
    response = api_client.post(
        "/api/tools/execute",
        json={
            "tool_name": "execute_terminal",
            "arguments": {"command": "ls -la"},
            "user_confirmed": True,  # client boolean must be ignored
        },
    )
    assert response.status_code == 403
    assert "Approval token required" in response.json()["detail"]


def test_api_approval_request_and_execute_flow(api_client: TestClient) -> None:
    # 1. Request approval token from server
    token_resp = api_client.post(
        "/api/v1/approvals/request",
        json={
            "tool_name": "execute_terminal",
            "arguments": {"command": "whoami"},
        },
    )
    assert token_resp.status_code == 200
    token_data = token_resp.json()
    assert "approval_token" in token_data
    assert "expires_at" in token_data
    token = token_data["approval_token"]

    with patch("asyncio.create_subprocess_shell") as mock_exec:
        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (b"nexus-operator\n", b"")
        mock_proc.returncode = 0
        mock_exec.return_value = mock_proc

        # 2. Execute tool with X-Approval-Token header -> 200 OK
        exec_resp = api_client.post(
            "/api/tools/execute",
            json={
                "tool_name": "execute_terminal",
                "arguments": {"command": "whoami"},
            },
            headers={"X-Approval-Token": token},
        )
        assert exec_resp.status_code == 200
        assert exec_resp.json()["success"] is True

        # 3. Replay with the same consumed token -> 403 Forbidden
        replay_resp = api_client.post(
            "/api/tools/execute",
            json={
                "tool_name": "execute_terminal",
                "arguments": {"command": "whoami"},
            },
            headers={"X-Approval-Token": token},
        )
        assert replay_resp.status_code == 403
        assert "replay detected" in replay_resp.json()["detail"].lower()


def test_api_cors_hardening(api_client: TestClient) -> None:
    # Verify CORS does not return wildcard *
    response = api_client.get(
        "/api/status",
        headers={"Origin": "http://localhost:8000"},
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:8000"
    assert response.headers.get("access-control-allow-origin") != "*"
