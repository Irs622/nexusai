"""Configuration Loader & Pydantic Settings for NexusAI."""

from __future__ import annotations

from pathlib import Path
from typing import Any
import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from nexusai.core.errors import ConfigurationError
from nexusai.tools.plugin_manifest import PluginCapabilities

_env_file = Path.cwd() / ".env"
if _env_file.is_file():
    load_dotenv(dotenv_path=_env_file)


class AppSettings(BaseModel):
    name: str = "NexusAI"
    version: str = "0.1.0"
    environment: str = "development"
    debug: bool = True


class LoggingSettings(BaseModel):
    level: str = "INFO"
    format: str = "{time} | {level} | {message}"
    file_path: str = "logs/nexusai.log"
    audit_log_path: str = "logs/audit.log"
    rotation: str = "10 MB"


class ModelSettings(BaseModel):
    default_provider: str = "openai"
    default_model: str = "gpt-4o"
    base_url: str | None = None
    temperature: float = 0.7
    max_tokens: int = 2048
    timeout_seconds: int = 30


class SecuritySettings(BaseModel):
    strict_mode: bool = True
    auto_approve_low_risk: bool = True
    isolation_timeout_seconds: float = 30.0
    capabilities: PluginCapabilities = Field(default_factory=PluginCapabilities)
    forbidden_commands: list[str] = Field(default_factory=list)
    protected_paths: list[str] = Field(default_factory=list)


class PathSettings(BaseModel):
    workspace_dir: str = ".nexusai"
    plugins_dir: str = "plugins"
    storage_dir: str = "storage"


class SystemConfig(BaseSettings):
    app: AppSettings = Field(default_factory=AppSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    models: ModelSettings = Field(default_factory=ModelSettings)
    security: SecuritySettings = Field(default_factory=SecuritySettings)
    paths: PathSettings = Field(default_factory=PathSettings)

    model_config = SettingsConfigDict(
        env_file=str(_env_file) if _env_file.is_file() else None,
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
    )

    @classmethod
    def load_from_yaml(cls, config_dir: str | Path = "config") -> SystemConfig:
        """Load configuration settings from YAML files (e.g. default.yaml) in target directory."""
        config_path = Path(config_dir)
        yaml_file = config_path / "default.yaml" if config_path.is_dir() else config_path

        if not yaml_file.exists():
            return cls()

        try:
            with open(yaml_file, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            return cls.model_validate(data)
        except Exception as e:
            raise ConfigurationError(f"Failed to parse YAML configuration: {e}") from e
