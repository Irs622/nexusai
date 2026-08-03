"""Plugin Manifest Schema & Capability Security Model."""
from typing import List, Optional
from pydantic import BaseModel, Field

class PluginCapabilities(BaseModel):
    """Capabilities requested by a plugin before execution."""
    read_filesystem: bool = False
    write_filesystem: bool = False
    terminal_execution: bool = False
    network_http: bool = False
    applescript: bool = False

class PluginManifest(BaseModel):
    """Manifest schema defining plugin identity, requirements, and permissions."""
    name: str = Field(..., description="Plugin package name")
    version: str = Field(..., description="Plugin version (SemVer)")
    nexusai_sdk_version: str = Field(default=">=0.1.0", description="Target NexusAI SDK version requirement")
    description: str = Field(default="", description="Plugin description")
    entrypoint: str = Field(..., description="Python dot path to plugin class")
    capabilities: PluginCapabilities = Field(default_factory=PluginCapabilities)
    dependencies: List[str] = Field(default_factory=list)
