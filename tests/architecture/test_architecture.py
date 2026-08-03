"""Architecture Fitness Tests enforcing Architectural Invariants and Import Boundaries."""

import ast
import inspect
from pathlib import Path
import pytest

from nexusai.providers.base import BaseProvider


def _get_ast_imports(file_path: Path) -> list[str]:
    """Parse a python file and extract all imported module names."""
    tree = ast.parse(file_path.read_text(), filename=str(file_path))
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module)
    return imports


def test_provider_adapter_isolation_rule() -> None:
    """Architecture Invariant: No provider file may import another provider adapter file."""
    providers_dir = Path("src/nexusai/providers")
    for file_path in providers_dir.glob("*.py"):
        imports = _get_ast_imports(file_path)
        for imp in imports:
            assert not imp.startswith("nexusai.providers.openai_provider"), f"Forbidden import in {file_path.name}: {imp}"
            assert not imp.startswith("nexusai.providers.gemini"), f"Forbidden import in {file_path.name}: {imp}"


def test_layer_boundary_rule() -> None:
    """Architecture Invariant: Runtime Kernel and Provider SDK must not import higher-level application layers."""
    check_dirs = [Path("src/nexusai/providers"), Path("src/nexusai/runtime")]
    forbidden_layers = ["nexusai.cli", "nexusai.brain"]
    for dir_path in check_dirs:
        for file_path in dir_path.glob("*.py"):
            imports = _get_ast_imports(file_path)
            for imp in imports:
                for forbidden in forbidden_layers:
                    assert not imp.startswith(forbidden), f"Layer Boundary Violation in {file_path.name}: imports {imp}"


def test_engine_adapter_decoupling_rule() -> None:
    """Architecture Invariant: ExecutionEngine must not import concrete provider adapter implementations."""
    engine_path = Path("src/nexusai/runtime/engine.py")
    imports = _get_ast_imports(engine_path)
    forbidden_adapters = ["nexusai.providers.mock", "nexusai.providers.openrouter", "nexusai.providers.gemini"]
    for imp in imports:
        for forbidden in forbidden_adapters:
            assert not imp.startswith(forbidden), f"ExecutionEngine Decoupling Violation: imports {imp}"


def test_domain_models_import_rule() -> None:
    """Architecture Invariant: Core domain models must not import third-party transport libraries."""
    models_path = Path("src/nexusai/providers/models.py")
    forbidden_transports = ["httpx", "aiohttp", "requests", "openai", "google", "anthropic"]
    imports = _get_ast_imports(models_path)
    for imp in imports:
        for forbidden in forbidden_transports:
            assert not imp.startswith(forbidden), f"Domain Model Transport Leak in {models_path.name}: imports {imp}"


def test_async_io_rule() -> None:
    """Architecture Invariant: Network/IO methods on BaseProvider interface must be async."""
    async_methods = ["chat", "stream_chat", "embeddings", "list_models", "health_check"]
    for method_name in async_methods:
        method = getattr(BaseProvider, method_name)
        assert inspect.iscoroutinefunction(method), f"Async IO Rule Violation: {method_name} must be a coroutine function"
