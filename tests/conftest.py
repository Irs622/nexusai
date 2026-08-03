"""
Pytest global fixtures.
"""

import pytest
from pathlib import Path
from nexusai.core.config import SystemConfig, SecuritySettings
from nexusai.core.container import DependencyContainer
from nexusai.bus.bus import CommandBus, QueryBus, EventBus
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
