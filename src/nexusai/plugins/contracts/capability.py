"""
Strongly-typed plugin capabilities abstractions.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class PluginCapabilityType(str, Enum):
    """Standard OS plugin capability types."""

    LLM_PROVIDER = "llm.provider"
    VECTOR_STORE = "vector.store"
    STT_PROVIDER = "speech.stt"
    TTS_PROVIDER = "speech.tts"
    MEMORY_STORE = "memory.store"
    WORKFLOW_ENGINE = "workflow.engine"
    AUTOMATION_DRIVER = "automation.driver"
    KNOWLEDGE_SOURCE = "knowledge.source"
    TOOL_INTEGRATION = "tool.integration"
    CUSTOM = "custom"


@dataclass(frozen=True)
class Capability:
    """Strongly-typed capability value object."""

    name: str
    version: str = "1.0.0"

    def __str__(self) -> str:
        return f"{self.name}:{self.version}"


class PluginCapability:
    """Standard capability constants and builder."""

    LLM_PROVIDER = Capability(PluginCapabilityType.LLM_PROVIDER.value)
    VECTOR_STORE = Capability(PluginCapabilityType.VECTOR_STORE.value)
    STT_PROVIDER = Capability(PluginCapabilityType.STT_PROVIDER.value)
    TTS_PROVIDER = Capability(PluginCapabilityType.TTS_PROVIDER.value)
    MEMORY_STORE = Capability(PluginCapabilityType.MEMORY_STORE.value)
    WORKFLOW_ENGINE = Capability(PluginCapabilityType.WORKFLOW_ENGINE.value)
    AUTOMATION_DRIVER = Capability(PluginCapabilityType.AUTOMATION_DRIVER.value)
    KNOWLEDGE_SOURCE = Capability(PluginCapabilityType.KNOWLEDGE_SOURCE.value)
    TOOL_INTEGRATION = Capability(PluginCapabilityType.TOOL_INTEGRATION.value)

    @classmethod
    def custom(cls, name: str, version: str = "1.0.0") -> Capability:
        """Create a custom capability descriptor."""
        return Capability(name=name, version=version)
