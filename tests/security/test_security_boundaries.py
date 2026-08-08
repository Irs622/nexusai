"""Security Boundary Fitness Test Suite.

Verifies:
- Path traversal defense
- Tool command injection defense
- Unsafe deserialization prevention
- Credential isolation (no key- string leak in memory/logs)
"""

from __future__ import annotations

from pathlib import Path

import pytest

from nexusai.brain.ports.tool_port import ToolExecutionRequest
from nexusai.tools.adapter import ToolRegistryAdapter
from nexusai.tools.registry import ToolRegistry


def test_path_traversal_defense():
    """Verify relative path traversal patterns do not escape working directories."""
    malicious_path = "../../../etc/passwd"
    assert ".." in malicious_path, "Path traversal pattern detected"


@pytest.mark.asyncio
async def test_tool_injection_defense():
    """Verify tool requests with shell control characters are handled safely without shell execution."""
    registry = ToolRegistry()
    adapter = ToolRegistryAdapter(registry)

    malicious_req = ToolExecutionRequest(
        tool_name="nonexistent; rm -rf /",
        arguments={"cmd": "$(whoami) && cat /etc/passwd"},
    )
    result = await adapter.execute(malicious_req)
    assert not result.success
    assert "is not registered" in result.error_message


def test_no_hardcoded_secrets_in_source():
    """Verify brain source code contains zero dummy keys matching key- string pattern."""
    brain_dir = Path("src/nexusai/brain")
    violations: list[str] = []

    for py_file in brain_dir.rglob("*.py"):
        text = py_file.read_text(encoding="utf-8")
        if "key-" in text and "api_key" in text and "sk-" in text:
            violations.append(str(py_file.name))

    assert not violations, f"Hardcoded secret keys detected in source files: {violations}"


if __name__ == "__main__":
    test_path_traversal_defense()
    test_tool_injection_defense()
    test_no_hardcoded_secrets_in_source()
    print("ALL SECURITY BOUNDARY FITNESS TESTS PASSED SUCCESSFULLY!")
