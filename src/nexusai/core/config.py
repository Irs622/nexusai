"""
Configuration Loader & Pydantic Settings for NexusAI.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from nexusai.core.errors import ConfigurationError

load_dotenv()


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
    forbidden_commands: list[str] = Field(default_factory=list)
    protected_paths: list[str] = Field(default_factory=list)


class PathSettings(BaseModel):
    workspace_dir: str = "~/.nexusai"
    plugins_dir: str = "plugins"
    storage_dir: str = "storage"


class SystemConfig(BaseSettings):
    app: AppSettings = Field(default_factory=AppSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    models: ModelSettings = Field(default_factory=ModelSettings)
    security: SecuritySettings = Field(default_factory=SecuritySettings)
    paths: PathSettings = Field(default_factory=PathSettings)

    model_config = SettingsConfigDict(
        env_prefix="NEXUS_AI_",
        env_nested_delimiter="__",
        extra="ignore",
    )

    @classmethod
    def load_from_yaml(cls, config_dir: Path | str = "config") -> "SystemConfig":
        """Load configuration from YAML files in the given directory."""
        config_path = Path(config_dir)
        default_file = config_path / "default.yaml"
        security_file = config_path / "security.yaml"

        data: dict[str, Any] = {}

        if default_file.exists():
            try:
                with open(default_file, "r", encoding="utf-8") as f:
                    yaml_data = yaml.safe_load(f) or {}
                    data.update(yaml_data)
            except Exception as e:
                raise ConfigurationError(f"Failed to parse {default_file}: {e}")

        if security_file.exists():
            try:
                with open(security_file, "r", encoding="utf-8") as f:
                    yaml_security = yaml.safe_load(f) or {}
                    if "security" in yaml_security:
                        data["security"] = yaml_security["security"]
            except Exception as e:
                raise ConfigurationError(f"Failed to parse {security_file}: {e}")

        try:
            return cls(**data)
        except Exception as e:
            raise ConfigurationError(f"Invalid configuration data: {e}")
