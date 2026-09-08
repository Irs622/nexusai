"""
Pytest global fixtures.
"""

from pathlib import Path

import pytest

from nexusai.bus.bus import CommandBus, EventBus, QueryBus
from nexusai.core.config import SecuritySettings, SystemConfig
from nexusai.core.container import DependencyContainer
from nexusai.security.guard import SecurityGuard


@pytest.fixture
def mock_config(tmp_path: Path) -> SystemConfig:
    """Fixture returning a valid SystemConfig instance."""
    config = SystemConfig()
    config.logging.file_path = str(tmp_path / "test.log")
    config.logging.audit_log_path = str(tmp_path / "audit.log")
    return config


@pytest.fixture
def container() -> DependencyContainer:
    """Fixture returning a fresh DependencyContainer."""
    return DependencyContainer()


@pytest.fixture
def security_guard() -> SecurityGuard:
    """Fixture returning a configured SecurityGuard instance."""
    settings = SecuritySettings(
        strict_mode=True,
        auto_approve_low_risk=True,
        forbidden_commands=["rm -rf /", "sudo rm -rf"],
        protected_paths=["/System", "/etc"],
    )
    return SecurityGuard(settings)


@pytest.fixture
def command_bus() -> CommandBus:
    return CommandBus()


@pytest.fixture
def query_bus() -> QueryBus:
    return QueryBus()


@pytest.fixture
def event_bus() -> EventBus:
    return EventBus()


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    for item in items:
        fspath = str(item.fspath)
        if "/tests/integration/" in fspath:
            item.add_marker(pytest.mark.integration)
        elif "/tests/stress/" in fspath:
            item.add_marker(pytest.mark.stress)
        elif "/tests/performance/" in fspath or "/tests/benchmarks/" in fspath:
            item.add_marker(pytest.mark.benchmark)
        elif "/tests/contract/" in fspath:
            item.add_marker(pytest.mark.contract)
        elif "/tests/security/" in fspath:
            item.add_marker(pytest.mark.security)
        elif "/tests/architecture/" in fspath:
            item.add_marker(pytest.mark.architecture)
        elif "/tests/unit/" in fspath:
            item.add_marker(pytest.mark.unit)
