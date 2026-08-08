"""
Unit tests for Configuration loader.
"""

from pathlib import Path

from nexusai.core.config import SystemConfig


def test_system_config_defaults() -> None:
    config = SystemConfig()
    assert config.app.name == "NexusAI"
    assert config.app.environment == "development"
    assert config.models.default_provider == "openai"


def test_load_from_yaml(tmp_path: Path) -> None:
    yaml_content = """
app:
  name: "CustomNexus"
  environment: "production"
models:
  default_provider: "anthropic"
  default_model: "claude-3.5-sonnet"
"""
    config_file = tmp_path / "default.yaml"
    config_file.write_text(yaml_content)

    config = SystemConfig.load_from_yaml(config_dir=tmp_path)
    assert config.app.name == "CustomNexus"
    assert config.app.environment == "production"
    assert config.models.default_provider == "anthropic"
    assert config.models.default_model == "claude-3.5-sonnet"
