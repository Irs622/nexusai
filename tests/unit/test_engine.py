"""Unit tests for NexusAIRuntimeEngine master orchestrator."""
import pathlib
import pytest
from nexusai.core.engine import NexusAIRuntimeEngine
from nexusai.core.config import SystemConfig

@pytest.mark.asyncio
async def test_runtime_engine_initialization_and_command_execution(tmp_path: pathlib.Path) -> None:
    config = SystemConfig()
    config.logging.file_path = str(tmp_path / "test_engine.log")
    config.logging.audit_log_path = str(tmp_path / "test_audit.log")
    
    engine = NexusAIRuntimeEngine(config)
    await engine.initialize()
    
    assert engine.registry is not None
    assert engine.command_bus is not None
    assert engine.event_bus is not None
    assert engine.security_guard is not None
