"""Ports and interfaces sub-package for NexusAI Agent Runtime."""

from nexusai.brain.ports.capability_discovery import (
    CapabilityAdvertisement,
    DynamicCapabilityGraphBuilder,
    RuntimeCapabilityDiscovery,
)
from nexusai.brain.ports.capability_registry import CapabilityProvider, ToolCapabilityRegistry
from nexusai.brain.ports.tool_port import IToolPort, ToolExecutionRequest, ToolExecutionResult

__all__ = [
    "CapabilityAdvertisement",
    "CapabilityProvider",
    "DynamicCapabilityGraphBuilder",
    "IToolPort",
    "RuntimeCapabilityDiscovery",
    "ToolCapabilityRegistry",
    "ToolExecutionRequest",
    "ToolExecutionResult",
]
