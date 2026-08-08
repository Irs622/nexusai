"""Architecture tests to enforce clean layer boundaries in NexusAI."""

import ast
import pathlib


def test_security_guard_does_not_import_ui() -> None:
    """Ensure security guard does not statically import CLI or API UI components."""
    guard_path = pathlib.Path("src/nexusai/security/guard.py")
    tree = ast.parse(guard_path.read_text())

    imported_modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported_modules.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported_modules.add(node.module)

    assert not any(
        "cli" in m or "api" in m for m in imported_modules
    ), f"Security guard has illegal UI imports: {imported_modules}"


def test_core_does_not_import_cli() -> None:
    """Ensure core infrastructure does not statically import CLI or API components."""
    core_path = pathlib.Path("src/nexusai/core/config.py")
    tree = ast.parse(core_path.read_text())

    imported_modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported_modules.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported_modules.add(node.module)

    assert not any(
        "cli" in m or "api" in m for m in imported_modules
    ), f"Core config has illegal UI imports: {imported_modules}"
