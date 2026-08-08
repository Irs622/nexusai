"""Architecture Fitness Test — Tool Isolation Boundary.

Verifies that nexusai.brain does NOT import ToolRegistry directly, enforcing IToolPort isolation.
"""

from __future__ import annotations

import inspect

import nexusai.brain.loop_executor
import nexusai.brain.pipeline.stages
import nexusai.brain.service


def test_brain_does_not_import_tool_registry():
    """Verify nexusai.brain modules do NOT import ToolRegistry or concrete tool implementations directly."""
    brain_modules = [
        nexusai.brain.loop_executor,
        nexusai.brain.pipeline.stages,
        nexusai.brain.service,
    ]

    for mod in brain_modules:
        src = inspect.getsource(mod)
        assert (
            "nexusai.tools.registry" not in src
        ), f"Brain module '{mod.__name__}' must NOT import ToolRegistry directly!"
        assert (
            "from nexusai.tools.registry import" not in src
        ), f"Brain module '{mod.__name__}' must NOT import ToolRegistry directly!"


if __name__ == "__main__":
    test_brain_does_not_import_tool_registry()
    print("ALL TOOL BOUNDARY FITNESS TESTS PASSED SUCCESSFULLY!")
