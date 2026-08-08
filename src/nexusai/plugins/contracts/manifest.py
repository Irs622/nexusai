"""
Plugin manifest data structures and parsing schema.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class PluginManifest(BaseModel):
    """Canonical plugin manifest model (schema for plugin.yaml/toml/json)."""

    id: str = Field(..., description="Unique plugin identifier (e.g. org.nexusai.llm.openrouter)")
    name: str = Field(..., description="Human-readable plugin name")
    version: str = Field(..., description="Semantic version string")
    api_version: str = Field(default="1.0.0", description="Plugin API contract version")

    # Multi-version API & Kernel compatibility
    kernel_api: int = Field(default=1, description="Target kernel API major version")
    plugin_api: int = Field(default=1, description="Target plugin API major version")
    minimum_kernel: str = Field(default="0.1.0", description="Minimum supported kernel version")
    tested_until: str | None = Field(default=None, description="Maximum tested kernel version")

    author: str = Field(default="Anonymous", description="Plugin author or organization")
    description: str = Field(default="", description="Detailed summary of plugin functionality")
    entrypoint: str = Field(
        ..., description="Python entrypoint class (e.g. module.submodule:MyPlugin)"
    )

    capabilities: list[str] = Field(
        default_factory=list, description="Capabilities provided by this plugin"
    )
    permissions: dict[str, Any] = Field(
        default_factory=dict, description="Scoped permissions required by plugin"
    )

    dependencies: list[str] = Field(
        default_factory=list, description="Required plugin ID dependencies"
    )
    optional_dependencies: list[str] = Field(
        default_factory=list, description="Optional plugin ID dependencies"
    )

    # Marketplace & Integrity metadata
    signature: str | None = Field(default=None, description="Digital signature of plugin author")
    publisher: str | None = Field(default=None, description="Verified publisher identifier")
    license: str = Field(default="MIT", description="Software license identifier")
    repository: str = Field(default="", description="Source code repository URL")
    homepage: str = Field(default="", description="Plugin website or documentation link")
    hash: str | None = Field(default=None, description="SHA256 package/manifest content digest")

    model_config = {
        "frozen": True,
        "arbitrary_types_allowed": True,
    }
