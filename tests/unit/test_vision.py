"""
Unit tests for Vision Layer, ScreenCaptureTool, and Multimodal OpenAI Provider processing.
"""

import base64
from pathlib import Path
import pytest
from unittest.mock import AsyncMock, patch

from nexusai.core.errors import ToolExecutionError
from nexusai.models.openai_provider import process_multimodal_messages
from nexusai.security.guard import RiskLevel
from nexusai.tools.registry import ToolRegistry
from nexusai.tools.vision.screen import ScreenCaptureTool


@pytest.mark.asyncio
async def test_screen_capture_tool_success() -> None:
    tool = ScreenCaptureTool()
    assert tool.name == "vision_capture_screen"
    assert tool.risk_level == RiskLevel.LOW

    mock_process = AsyncMock()
    mock_process.communicate.return_value = (b"", b"")
    mock_process.returncode = 0

    with patch("asyncio.create_subprocess_exec", return_value=mock_process) as mock_exec:
        result = await tool.execute()
        mock_exec.assert_called_once()
        assert result["type"] == "image_path"
        assert "nexusai_screenshot.png" in result["path"]


@pytest.mark.asyncio
async def test_screen_capture_tool_failure() -> None:
    tool = ScreenCaptureTool()

    mock_process = AsyncMock()
    mock_process.communicate.return_value = (b"", b"screencapture: permission denied")
    mock_process.returncode = 1

    with patch("asyncio.create_subprocess_exec", return_value=mock_process):
        with pytest.raises(ToolExecutionError) as exc_info:
            await tool.execute()

        assert "Screen capture failed with exit code 1" in str(exc_info.value)


@pytest.mark.asyncio
async def test_process_multimodal_messages(tmp_path: Path) -> None:
    dummy_img = tmp_path / "test_screen.png"
    dummy_bytes = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
    dummy_file = dummy_img
    dummy_file.write_bytes(dummy_bytes)

    messages = [
        {"role": "user", "content": "Look at this screenshot"},
        {"role": "tool", "content": f'{{"type": "image_path", "path": "{dummy_img}"}}'},
    ]

    formatted = await process_multimodal_messages(messages)
    assert len(formatted) == 2
    assert formatted[0]["content"] == "Look at this screenshot"

    multimodal_content = formatted[1]["content"]
    assert isinstance(multimodal_content, list)
    assert len(multimodal_content) == 2
    assert multimodal_content[0]["type"] == "text"
    assert multimodal_content[1]["type"] == "image_url"

    b64_expected = base64.b64encode(dummy_bytes).decode("utf-8")
    assert b64_expected in multimodal_content[1]["image_url"]["url"]


@pytest.mark.asyncio
async def test_process_multimodal_messages_missing_file() -> None:
    messages = [
        {"role": "tool", "content": '{"type": "image_path", "path": "/tmp/non_existent_12345.png"}'},
    ]

    formatted = await process_multimodal_messages(messages)
    assert "Screenshot file not found" in formatted[0]["content"]


def test_vision_tool_registry() -> None:
    registry = ToolRegistry()
    registry.register(ScreenCaptureTool())

    assert registry.has_tool("vision_capture_screen")
    schemas = registry.get_all_schemas()
    assert schemas[0]["function"]["name"] == "vision_capture_screen"
